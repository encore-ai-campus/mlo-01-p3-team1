#!/usr/bin/env python3
"""Resolve Kafka/S3A with Maven once, freeze SHA256, install without resolving again."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from config import ROOT


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    return h.hexdigest()


def modules(path):
    result = set()
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name.startswith('META-INF/maven/') and name.endswith('/pom.properties'):
                values = dict(line.split('=', 1) for line in z.read(name).decode().splitlines() if '=' in line and not line.startswith('#'))
                if 'artifactId' in values: result.add((values.get('groupId'), values['artifactId'], values.get('version')))
    return result


def distribution(spark_home):
    jars = Path(spark_home) / 'jars'
    if not jars.is_dir() or jars.is_symlink():
        raise ValueError('Verified Spark distribution jars required')
    result = []
    for path in sorted(jars.glob('*.jar')):
        if path.is_symlink(): raise ValueError('Symlink in Spark distribution')
        result.append({'filename': path.name, 'sha256': digest(path)})
    if not result: raise ValueError('Empty Spark distribution')
    return result


def prepare(spark_home, output, diagnostic_log=None):
    versions = json.loads((ROOT / 'versions.json').read_text())
    spark_home, output = Path(spark_home), Path(output)
    hadoop = versions['spark']['hadoop']
    if not (spark_home / 'jars' / f'hadoop-client-api-{hadoop}.jar').exists():
        raise ValueError('Use the verified Spark 4.1.3 Hadoop distribution')
    if output.exists(): raise ValueError('Output exists; preserve the old connector lock')
    if not shutil.which('mvn'): raise ValueError('Maven is required for preparation only; on Ubuntu install the signed maven package')
    coordinates = [versions['connectors'][key]['coordinate'] for key in ('kafka', 's3a')]
    baseline = distribution(spark_home)
    existing = set()
    for jar in (spark_home / 'jars').glob('*.jar'): existing.update(modules(jar))
    # Keep Spark's logging API/provider pair. Hadoop's older transitive API
    # must not be installed beside Spark's already supplied SLF4J 2.x API.
    pins = versions['connectors'].get('provided_dependencies', {})
    for coordinate, version in pins.items():
        group, artifact = coordinate.split(':')
        if (group, artifact, version) not in existing and not (spark_home/'jars'/(artifact+'-'+version+'.jar')).is_file():
            raise ValueError('Reviewed provided dependency missing from Spark: ' + coordinate)
        existing.add((group, artifact, version))
    with tempfile.TemporaryDirectory() as temporary:
        temp = Path(temporary); local_repo = temp / 'repository'
        dependencies = ''
        for coord in coordinates:
            group, artifact, version = coord.split(':')
            exclusions = '<exclusions><exclusion><groupId>org.apache.hadoop</groupId><artifactId>hadoop-common</artifactId></exclusion></exclusions>' if artifact == 'hadoop-aws' else ''
            dependencies += f'<dependency><groupId>{group}</groupId><artifactId>{artifact}</artifactId><version>{version}</version>{exclusions}</dependency>'
        pom = temp / 'pom.xml'
        management = ''.join('<dependency><groupId>' + key.split(':')[0] + '</groupId><artifactId>' + key.split(':')[1] + '</artifactId><version>' + version + '</version></dependency>' for key, version in pins.items())
        pom.write_text('<project><modelVersion>4.0.0</modelVersion><groupId>local.music</groupId><artifactId>connector-lock</artifactId><version>1</version><dependencyManagement><dependencies>' + management + '</dependencies></dependencyManagement><dependencies>' + dependencies + '</dependencies></project>')
        log = temp / 'maven.log'
        settings = temp / 'settings.xml'
        settings.write_text('<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0"><mirrors><mirror><id>reviewed-central</id><mirrorOf>*</mirrorOf><url>https://repo.maven.apache.org/maven2</url></mirror></mirrors></settings>\n')
        # Structured argv preserves spaces. Ignore user settings, mirrors and
        # environment-injected Maven arguments during this official resolution.
        env = {k: v for k, v in os.environ.items() if k not in ('MAVEN_ARGS', 'MAVEN_OPTS', 'JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS')}
        with log.open('w') as f:
            r = subprocess.run(['mvn', '-B', '-ntp', '--settings', str(settings), '--global-settings', str(settings),
                                '-f', str(pom), '-Dmaven.repo.local=' + str(local_repo),
                                'org.apache.maven.plugins:maven-dependency-plugin:3.8.1:build-classpath',
                                '-DincludeScope=runtime', '-Dmdep.outputFile=' + str(temp / 'classpath.txt')], stdout=f, stderr=f, env=env)
        if diagnostic_log:
            target = Path(diagnostic_log); target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(log, target); target.chmod(0o600)
        if r.returncode: raise ValueError('Official Maven resolution failed; no lock was published')
        jars, conflicts = [], []
        if diagnostic_log:
            coordinates_log=[]
            for text in (temp/'classpath.txt').read_text().strip().split(os.pathsep):
                rel=Path(text).resolve().relative_to(local_repo.resolve())
                coordinates_log.append(':'.join(('.'.join(rel.parts[:-3]),rel.parts[-3],rel.parts[-2])))
            target=Path(str(diagnostic_log)+'.resolved.json');target.write_text(json.dumps(coordinates_log,indent=2)+'\n');target.chmod(0o600)
        for text in (temp / 'classpath.txt').read_text().strip().split(os.pathsep):
            path = Path(text).resolve(); rel = path.relative_to(local_repo.resolve())
            group, artifact, version = '.'.join(rel.parts[:-3]), rel.parts[-3], rel.parts[-2]
            if version.endswith('-SNAPSHOT'): raise ValueError('SNAPSHOT dependency not allowed')
            # Spark/Scala itself is supplied by the distribution, never by a second pip/JAR installation.
            if group == 'org.scala-lang' or group == 'org.apache.spark' and artifact not in ('spark-sql-kafka-0-10_2.13', 'spark-token-provider-kafka-0-10_2.13'):
                if (group, artifact, version) not in existing and not (spark_home/'jars'/path.name).is_file():
                    conflicts.append(':'.join((group,artifact,version)))
                continue
            same = [m for m in existing if m[:2] == (group, artifact)]
            if same:
                if all(m[2] != version for m in same): conflicts.append(':'.join((group,artifact,version)))
                continue
            destination = spark_home / 'jars' / path.name
            if destination.exists():
                if digest(destination) != digest(path): raise ValueError('Same-name JAR content differs from the distribution')
                continue
            if any((spark_home/'jars').glob(artifact+'-*.jar')):
                conflicts.append(':'.join((group,artifact,version)));continue
            jars.append({'filename': path.name, 'coordinate': ':'.join((group, artifact, version)), 'sha256': digest(path), 'source': path})
        if conflicts: raise ValueError('Dependencies differ from supplied Spark jars: '+', '.join(sorted(set(conflicts))))
        names = [j['filename'] for j in jars]
        if len(names) != len(set(names)): raise ValueError('Duplicate resolved JAR filenames')
        output.parent.mkdir(parents=True, exist_ok=True)
        manifest = {'schema_version': 2, 'spark_version': versions['spark']['version'], 'hadoop_version': hadoop,
                    'distribution_jars': baseline, 'provided_dependencies': pins,
                    'coordinates': coordinates, 'jars': jars, 'elasticsearch': versions['connectors']['elasticsearch'],
                    'trust': 'Initial Maven resolution over HTTPS; SHA256 freezes the resulting bytes. Review this lock before fleet installation.'}
        with tempfile.TemporaryDirectory(dir=output.parent) as staging:
            staging = Path(staging)
            for jar in jars: shutil.copyfile(jar.pop('source'), staging / jar['filename'])
            (staging / 'connectors.lock.json').write_text(json.dumps(manifest, indent=2) + '\n')
            validate_bundle(staging, spark_home)
            # Rename only a complete bundle; never expose a partial lock.
            staging.rename(output)
    print('Kafka/S3A dependency lock prepared; ES connector remains unresolved.')


def validate_bundle(directory, spark_home=None, reviewed_lock=None):
    directory = Path(directory)
    lock = directory / 'connectors.lock.json'
    if directory.is_symlink() or lock.is_symlink(): raise ValueError('Symlink connector bundle')
    manifest = json.loads(lock.read_text())
    if manifest.get('schema_version') != 2: raise ValueError('Reviewed schema 2 connector lock required')
    if reviewed_lock is not None and manifest != json.loads(Path(reviewed_lock).read_text()):
        raise ValueError('Bundle differs from reviewed connector lock')
    versions = json.loads((ROOT / 'versions.json').read_text())
    if manifest['spark_version'] != versions['spark']['version'] or manifest['hadoop_version'] != versions['spark']['hadoop']:
        raise ValueError('Connector lock belongs to a different Spark/Hadoop runtime')
    expected = [versions['connectors'][k]['coordinate'] for k in ('kafka', 's3a')]
    if manifest['coordinates'] != expected: raise ValueError('Connector coordinate lock differs')
    if manifest.get('provided_dependencies') != versions['connectors'].get('provided_dependencies', {}):
        raise ValueError('Provided dependency selection differs from review')
    entries = manifest['jars']
    if not entries or len({j['filename'] for j in entries}) != len(entries): raise ValueError('Empty/duplicate connector lock')
    roots = set(expected)
    if not roots <= {j.get('coordinate') for j in entries}: raise ValueError('Required connector root missing from lock')
    baseline = manifest['distribution_jars']
    if not baseline or len({j['filename'] for j in baseline}) != len(baseline): raise ValueError('Invalid distribution lock')
    if {j['filename'] for j in baseline} & {j['filename'] for j in entries}: raise ValueError('Connector replaces distribution jar')
    for jar in entries:
        coordinate = jar.get('coordinate', '')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+', coordinate) or coordinate.endswith('-SNAPSHOT'):
            raise ValueError('Invalid or nonrelease connector coordinate')
        artifact = coordinate.split(':')[1]
        if ':'.join(coordinate.split(':')[:2]) in manifest['provided_dependencies'] or any(j['filename'].startswith(artifact+'-') for j in baseline):
            raise ValueError('Connector duplicates a supplied distribution artifact')
    for jar in [*baseline, *entries]:
        if not re.fullmatch(r'[A-Za-z0-9_.-]+\.jar', jar['filename']) or not re.fullmatch(r'[0-9a-f]{64}', jar['sha256']):
            raise ValueError('Invalid connector/distribution lock entry')
    if spark_home is not None:
        spark_home = Path(spark_home)
        if (spark_home/'jars').is_symlink() or not (spark_home/'jars').is_dir(): raise ValueError('Unsafe Spark jar directory')
        allowed = {j['filename'] for j in [*baseline, *entries]}
        if any(p.name not in allowed for p in (spark_home/'jars').glob('*.jar')): raise ValueError('Unreviewed extra Spark jar')
        for jar in baseline:
            path = spark_home/'jars'/jar['filename']
            if path.is_symlink() or not path.is_file() or digest(path) != jar['sha256']:
                raise ValueError('Spark distribution differs from connector lock')
    sources = []
    for jar in entries:
        name = jar['filename']
        if not re.fullmatch(r'[A-Za-z0-9_.-]+\.jar', name) or not re.fullmatch(r'[0-9a-f]{64}', jar['sha256']):
            raise ValueError('Invalid connector lock entry')
        source = directory / name
        if source.is_symlink() or digest(source) != jar['sha256']: raise ValueError('Connector checksum mismatch')
        if spark_home is not None:
            destination = spark_home / 'jars' / name
            if destination.is_symlink() or destination.exists() and digest(destination) != jar['sha256']: raise ValueError('Existing JAR differs; explicit upgrade required')
            sources.append((source, destination))
    return manifest, sources


def install(directory, spark_home):
    reviewed = ROOT.parent/'connectors.lock.json'
    if not reviewed.is_file(): raise ValueError('Published reviewed connector lock required')
    manifest, sources = validate_bundle(directory, spark_home, reviewed)
    if (Path(spark_home)/'connectors.lock.json').is_symlink(): raise ValueError('Unsafe installed connector lock')
    # Verify the entire lock before copying any file.
    for source, destination in sources:
        if not destination.exists(): shutil.copyfile(source, destination); destination.chmod(0o644)
    shutil.copyfile(Path(directory) / 'connectors.lock.json', Path(spark_home) / 'connectors.lock.json')
    print('Checksum-locked Kafka/S3A JARs installed; no online dependency resolution occurred.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('prepare', 'install')); p.add_argument('--spark-home', required=True); p.add_argument('--directory', required=True)
    p.add_argument('--diagnostic-log')
    a = p.parse_args()
    try:
        if a.action == 'prepare': prepare(a.spark_home, a.directory, a.diagnostic_log)
        else: install(a.directory, a.spark_home)
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as error:
        print('[FAIL] ' + str(error), file=sys.stderr); sys.exit(1)
