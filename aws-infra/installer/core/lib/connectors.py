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


def prepare(spark_home, output):
    versions = json.loads((ROOT / 'versions.json').read_text())
    spark_home, output = Path(spark_home), Path(output)
    hadoop = versions['spark']['hadoop']
    if not (spark_home / 'jars' / f'hadoop-client-api-{hadoop}.jar').exists():
        raise ValueError('Use the verified Spark 4.1.3 Hadoop distribution')
    if output.exists(): raise ValueError('Output exists; preserve the old connector lock')
    if not shutil.which('mvn'): raise ValueError('Maven is required for preparation only; on Ubuntu install the signed maven package')
    coordinates = [versions['connectors'][key]['coordinate'] for key in ('kafka', 's3a')]
    existing = set()
    for jar in (spark_home / 'jars').glob('*.jar'): existing.update(modules(jar))
    with tempfile.TemporaryDirectory() as temporary:
        temp = Path(temporary); local_repo = temp / 'repository'
        dependencies = ''
        for coord in coordinates:
            group, artifact, version = coord.split(':')
            exclusions = '<exclusions><exclusion><groupId>org.apache.hadoop</groupId><artifactId>hadoop-common</artifactId></exclusion></exclusions>' if artifact == 'hadoop-aws' else ''
            dependencies += f'<dependency><groupId>{group}</groupId><artifactId>{artifact}</artifactId><version>{version}</version>{exclusions}</dependency>'
        pom = temp / 'pom.xml'
        pom.write_text('<project><modelVersion>4.0.0</modelVersion><groupId>local.music</groupId><artifactId>connector-lock</artifactId><version>1</version><dependencies>' + dependencies + '</dependencies></project>')
        log = temp / 'maven.log'
        with log.open('w') as f:
            r = subprocess.run(['mvn', '-B', '-ntp', '-f', str(pom), '-Dmaven.repo.local=' + str(local_repo),
                                'org.apache.maven.plugins:maven-dependency-plugin:3.8.1:build-classpath',
                                '-DincludeScope=runtime', '-Dmdep.outputFile=' + str(temp / 'classpath.txt')], stdout=f, stderr=f)
        if r.returncode: raise ValueError('Official Maven resolution failed; no lock was published')
        jars = []
        for text in (temp / 'classpath.txt').read_text().strip().split(os.pathsep):
            path = Path(text).resolve(); rel = path.relative_to(local_repo.resolve())
            group, artifact, version = '.'.join(rel.parts[:-3]), rel.parts[-3], rel.parts[-2]
            # Spark/Scala itself is supplied by the distribution, never by a second pip/JAR installation.
            if group == 'org.scala-lang' or group == 'org.apache.spark' and artifact not in ('spark-sql-kafka-0-10_2.13', 'spark-token-provider-kafka-0-10_2.13'):
                continue
            same = [m for m in existing if m[:2] == (group, artifact)]
            if same:
                if all(m[2] != version for m in same): raise ValueError('Transitive version conflicts with Spark: ' + group + ':' + artifact)
                continue
            destination = spark_home / 'jars' / path.name
            if destination.exists():
                if digest(destination) != digest(path): raise ValueError('Same-name JAR content differs from the distribution')
                continue
            jars.append({'filename': path.name, 'coordinate': ':'.join((group, artifact, version)), 'sha256': digest(path), 'source': path})
        names = [j['filename'] for j in jars]
        if len(names) != len(set(names)): raise ValueError('Duplicate resolved JAR filenames')
        output.mkdir(parents=True)
        for jar in jars: shutil.copyfile(jar.pop('source'), output / jar['filename'])
        manifest = {'schema_version': 1, 'spark_version': versions['spark']['version'], 'hadoop_version': hadoop,
                    'coordinates': coordinates, 'jars': jars, 'elasticsearch': versions['connectors']['elasticsearch'],
                    'trust': 'Initial Maven resolution over HTTPS; SHA256 freezes the resulting bytes. Review this lock before fleet installation.'}
        (output / 'connectors.lock.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Kafka/S3A dependency lock prepared; ES connector remains unresolved.')


def install(directory, spark_home):
    directory, spark_home = Path(directory), Path(spark_home)
    manifest = json.loads((directory / 'connectors.lock.json').read_text())
    versions = json.loads((ROOT / 'versions.json').read_text())
    if manifest['spark_version'] != versions['spark']['version'] or manifest['hadoop_version'] != versions['spark']['hadoop']:
        raise ValueError('Connector lock belongs to a different Spark/Hadoop runtime')
    expected = [versions['connectors'][k]['coordinate'] for k in ('kafka', 's3a')]
    if manifest['coordinates'] != expected: raise ValueError('Connector coordinate lock differs')
    entries = manifest['jars']
    if not entries or len({j['filename'] for j in entries}) != len(entries): raise ValueError('Empty/duplicate connector lock')
    sources = []
    for jar in entries:
        name = jar['filename']
        if not re.fullmatch(r'[A-Za-z0-9_.-]+\.jar', name) or not re.fullmatch(r'[0-9a-f]{64}', jar['sha256']):
            raise ValueError('Invalid connector lock entry')
        source, destination = directory / name, spark_home / 'jars' / name
        if source.is_symlink() or digest(source) != jar['sha256']: raise ValueError('Connector checksum mismatch')
        if destination.exists() and digest(destination) != jar['sha256']: raise ValueError('Existing JAR differs; explicit upgrade required')
        sources.append((source, destination))
    # Verify the entire lock before copying any file.
    for source, destination in sources:
        if not destination.exists(): shutil.copyfile(source, destination); destination.chmod(0o644)
    shutil.copyfile(directory / 'connectors.lock.json', spark_home / 'connectors.lock.json')
    print('Checksum-locked Kafka/S3A JARs installed; no online dependency resolution occurred.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('prepare', 'install')); p.add_argument('--spark-home', required=True); p.add_argument('--directory', required=True)
    a = p.parse_args()
    try:
        (prepare if a.action == 'prepare' else lambda home, output: install(output, home))(a.spark_home, a.directory)
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as error:
        print('[FAIL] ' + str(error), file=sys.stderr); sys.exit(1)
