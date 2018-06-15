# needs pip install cassandra-driver

import sys
from pyspark.context import SparkConf
from pyspark_cassandra import CassandraSparkContext
from helpers import *


def enforce_schema(msg):
    fields = msg.split(',')
    res = {}

    lon, lat = map(float, fields[10:12])
    res["passengers"] = int(fields[7])
    res["time_slot"] = determine_time_slot(fields[5])
    res["block_id"], res["sub_block_id"] = determine_block_ids(lon, lat)


    if res["block_id"] < 0 or res["time_slot"] < 0:
        return

    return res


def enforce_schema_by_header(msg, headerdict):
    fields = msg.split(',')
    res = {}

    lon, lat, psg, dt = map(lambda name: fields[headerdict[name]],
                            ["pickup_longitude", "pickup_latitude", "passenger_count", "pickup_datetime"])

    try:
        lon, lat = map(float, [lon, lat])
        res["passengers"] = int(psg)
        res["time_slot"] = determine_time_slot(dt)
        res["block_id"], res["sub_block_id"] = determine_block_ids(lon, lat)
    except:
        return

    if res["block_id"] < 0 or res["time_slot"] < 0:
        return

    return res


def infer_headerdict(headerstr, separator):
    return {s:i for i, s in enumerate(headerstr.split(separator))}


def get_s3_bucket_and_folder(configfile):
    with open(configfile) as fin:
        config = {row[0]:row[1] for row in map(lambda s: s.strip().split('='), fin.readlines())}
    return config['BUCKET'], config['FOLDER']



if __name__ == '__main__':

    if len(sys.argv) != 3:
        sys.exit(-1)

    keyspace, table = sys.argv[1:3]

    conf = SparkConf()
    conf.set("spark.cassandra.connection.host", "127.0.0.1")
    sc = CassandraSparkContext(conf=conf)

    bucketname, foldername = get_s3_bucket_and_folder('s3config')
    data = sc.textFile("s3a://{}/{}/*.csv".format(bucketname, foldername))

    (data.map(lambda x: enforce_schema(x))
         .filter(lambda x: x is not None)
         .map(lambda x: ((x["block_id"], x["time_slot"], x["sub_block_id"]), x["passengers"]))
         .reduceByKey(lambda x,y : x+y)
         .map(lambda x: ((x[0][0], x[0][1]), [x[0][2], x[1]]))
         .groupByKey()
         .map(lambda x: {"block_id": x[0][0], "time_slot": x[0][1], "subblock_psgcnt": sorted(x[1], key=lambda z: -z[1])[:10]})
         .saveToCassandra(keyspace, table))
