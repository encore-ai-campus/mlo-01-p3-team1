"""Assert actual PySpark executor work on the standalone cluster."""
from pyspark.sql import SparkSession

spark = SparkSession.builder.appName('music-cluster-smoke').getOrCreate()
try:
    assert spark.range(10000, numPartitions=9).selectExpr('sum(id) AS total').first().total == 49995000
    print('[PASS] Distributed PySpark job completed using the installed runtime')
finally:
    spark.stop()
