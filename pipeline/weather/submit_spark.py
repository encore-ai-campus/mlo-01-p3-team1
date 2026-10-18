"""EC2의 설치된 spark-submit으로 실행. 코드 ZIP만 executor에 전달."""
import os
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent

def connector_arguments():
    """Use the reviewed fleet JARs; dependency resolution is never implicit."""
    lock_path=os.environ.get('SPARK_CONNECTOR_LOCK','')
    spark_home=os.environ.get('SPARK_HOME','')
    if not lock_path or not spark_home:
        raise RuntimeError('SPARK_CONNECTOR_LOCK_and_SPARK_HOME_required')
    lock=json.loads(Path(lock_path).read_text(encoding='utf-8'))
    if (lock.get('schema_version')!=2 or lock.get('spark_version')!='4.1.3'
            or lock.get('hadoop_version')!='3.4.2'
            or 'org.apache.spark:spark-sql-kafka-0-10_2.13:4.1.3' not in lock.get('coordinates',[])):
        raise RuntimeError('incompatible_spark_connector_lock')
    entries=lock.get('distribution_jars',[])+lock.get('jars',[])
    if not lock.get('distribution_jars') or not lock.get('jars'):
        raise RuntimeError('incomplete_spark_connector_lock')
    jar_dir=Path(spark_home)/'jars'
    seen=set()
    for entry in entries:
        name=entry.get('filename','')
        if name!=Path(name).name or not name.endswith('.jar') or name in seen:
            raise RuntimeError('invalid_spark_connector_filename')
        seen.add(name)
        jar=jar_dir/name
        if not jar.is_file() or jar.is_symlink():
            raise RuntimeError('spark_connector_missing')
        with jar.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        if actual!=entry.get('sha256'):raise RuntimeError('spark_connector_checksum_mismatch')
    if {p.name for p in jar_dir.glob('*.jar')}!=seen:
        raise RuntimeError('unreviewed_spark_jar')
    if os.environ.get('SPARK_KAFKA_PACKAGE'):
        raise RuntimeError('SPARK_KAFKA_PACKAGE_conflicts_with_reviewed_lock')
    return []

def runtime_arguments():
    """Do not let an unreadable private config silently disable fleet authentication."""
    directory=os.environ.get('SPARK_CONF_DIR','')
    if not directory:
        raise RuntimeError('SPARK_CONF_DIR_required')
    properties=Path(directory)/'spark-defaults.conf'
    try:
        lines=properties.read_text(encoding='utf-8').splitlines()
    except OSError:
        raise RuntimeError('spark_runtime_configuration_unreadable') from None
    values={}
    for line in lines:
        if not line.strip() or line.lstrip().startswith('#'):continue
        parts=line.split(None,1)
        if len(parts)!=2 or parts[0] in values:raise RuntimeError('invalid_spark_runtime_configuration')
        values[parts[0]]=parts[1].strip()
    if (values.get('spark.authenticate')!='true' or not values.get('spark.authenticate.secret')
            or values.get('spark.network.crypto.enabled')!='true'):
        raise RuntimeError('authenticated_encrypted_spark_runtime_required')
    return ['--properties-file',str(properties)]


def build_package(output=None):
    output = Path(output) if output is not None else ROOT / 'runtime' / 'weather-code.zip'
    output.parent.mkdir(parents=True, exist_ok=True)
    # 원천·환경값·로그·다른 담당 파일은 압축하지 않음.
    sources = list(ROOT.glob('*.py')) + list(ROOT.glob('*.json'))
    sources += list(ROOT.glob('*.sql'))
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.write(ROOT.parent / '__init__.py', 'pipeline/__init__.py')
        archive.write(ROOT.parent / 'kafka_config.py', 'pipeline/kafka_config.py')
        archive.write(ROOT.parent / 'environment.py', 'pipeline/environment.py')
        for path in sorted(sources):
            archive.write(path, 'pipeline/weather/' + path.relative_to(ROOT).as_posix())
    return output

def main():
    from pipeline.environment import load
    load('weather')
    if not os.environ.get('SPARK_MASTER'):
        raise RuntimeError('SPARK_MASTER_missing')
    arguments=connector_arguments()+runtime_arguments()
    package_path=os.environ.get('WEATHER_SPARK_PACKAGE_PATH')
    archive = build_package(package_path)
    command = [os.environ.get('SPARK_SUBMIT') or 'spark-submit',
        '--master', os.environ['SPARK_MASTER'], '--deploy-mode', 'client',
        *arguments, '--py-files', str(archive)]
    if os.environ.get('SPARK_DRIVER_HOST'):
        command.extend(['--conf', 'spark.driver.host=' + os.environ['SPARK_DRIVER_HOST']])
    command.append(str(ROOT/'spark_job.py'))
    raise SystemExit(subprocess.call(command))

if __name__ == '__main__':
    main()
