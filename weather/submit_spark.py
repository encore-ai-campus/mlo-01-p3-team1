"""EC2의 설치된 spark-submit으로 실행. 코드 ZIP만 executor에 전달."""
import os
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent

def build_package():
    output = ROOT / 'runtime' / 'weather-code.zip'
    output.parent.mkdir(parents=True, exist_ok=True)
    # 원천·환경값·로그·다른 담당 파일은 압축하지 않음.
    sources = list(ROOT.glob('*.py')) + list((ROOT/'pipeline').glob('*.py'))
    sources += list((ROOT/'pipeline').glob('*.json'))
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(sources):
            archive.write(path, 'weather/' + path.relative_to(ROOT).as_posix())
    return output

def main():
    if not os.environ.get('SPARK_MASTER'):
        raise RuntimeError('SPARK_MASTER_missing')
    archive = build_package()
    command = [os.environ.get('SPARK_SUBMIT') or 'spark-submit',
        '--master', os.environ['SPARK_MASTER'], '--deploy-mode', 'client',
        '--packages', os.environ.get('SPARK_KAFKA_PACKAGE') or
            'org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.6',
        '--py-files', str(archive)]
    if os.environ.get('SPARK_DRIVER_HOST'):
        command.extend(['--conf', 'spark.driver.host=' + os.environ['SPARK_DRIVER_HOST']])
    command.append(str(ROOT/'pipeline/spark_job.py'))
    raise SystemExit(subprocess.call(command))

if __name__ == '__main__':
    main()
