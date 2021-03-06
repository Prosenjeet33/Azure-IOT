# Databricks notebook source
# MAGIC %md # IoT Central streaming to Azure Databricks
# MAGIC 
# MAGIC This python script is an example of how [IoT Central](https://azure.microsoft.com/services/iot-central/) can stream data to [Azure Databricks](https://azure.microsoft.com/services/databricks/) using Apache Spark. 
# MAGIC 
# MAGIC When this notebook runs in a Databricks workspace, the Python script:
# MAGIC 
# MAGIC 1. Reads the streaming measurement data from from an IoT Central application.
# MAGIC 1. Plots averaged humidity data by device to show a smoother plot.
# MAGIC 1. Stores the data in the cluster.
# MAGIC 1. Displays box plots with any outliers from the stored data.
# MAGIC 
# MAGIC ## Configuring event hub connection strings
# MAGIC 
# MAGIC IoT Central can be set up to export data to Azure Event Hubs using the **Continuous data export** feature. This example uses a single event hub for streaming telemetry. 
# MAGIC 
# MAGIC The connection string in the following cell is for the telemetry event hub. For more information, see the how-to guide [Extend Azure IoT Central with custom analytics](https://docs.microsoft.com/azure/iot-central/howto-create-custom-analytics).

# COMMAND ----------

from pyspark.sql.functions import *
from pyspark.sql.types import *

###### Event Hub Connection string ######
telementryEventHubConfig = {
  'eventhubs.connectionString' : '{your Event Hubs connection string}'
}

# COMMAND ----------

# MAGIC %md ## Telemetry query
# MAGIC #### Initial query
# MAGIC 
# MAGIC This creates a streaming DataFrame from the telemtry event hub. A streaming DataFrame continuously updates as more data arrives.

# COMMAND ----------

telemetryDF = spark \
  .readStream \
  .format("eventhubs") \
  .options(**telementryEventHubConfig) \
  .load()



# COMMAND ----------

# MAGIC %md #### Extract the required data
# MAGIC This creates a new streaming DataFrame that contains the:
# MAGIC - `deviceId` from the event hub message body
# MAGIC - `enqueuedTime` from the event hub message body
# MAGIC - `humidity` from the event hub message body
# MAGIC 
# MAGIC The code converts the binary body field to JSON and then extracts the required fields from the JSON.
# MAGIC 
# MAGIC The `sourceSchema` structure is a partial schema for the `body` field that defines just the fields you need.

# COMMAND ----------



# COMMAND ----------

# Create a schema that describes the Body field
sourceSchema = StructType([
  StructField("deviceId", StringType(), True),
  StructField("enqueuedTime", TimestampType(), True),
  StructField("telemetry", StructType([
    StructField('humidity', FloatType(), True),
    StructField('temperature', FloatType(), True),
    StructField('pressure', FloatType(), True)
  ])),
])

# Convert the binary Body column to a string
telemetryDF = telemetryDF.withColumn("body", col("Body").cast("string")).select(col('body'))

# Convert the string to JSON and select the fields you need.
jsonOptions = {"dateFormat" : "yyyy-MM-dd HH:mm:ss.SSS"}
telemetryDF = telemetryDF.withColumn("Body", from_json(telemetryDF.body, sourceSchema, jsonOptions)) \
  .select(col('body.deviceId'),col('body.enqueuedTime'),col('body.telemetry.humidity'), \
  col('body.telemetry.temperature'),col('body.telemetry.pressure'))

# display(telemetryDF)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Plot the telemetry
# MAGIC 
# MAGIC The following code uses a window to calculate rolling averages by device Id.
# MAGIC 
# MAGIC Because the example is still using a streaming DataFrame, the chart updates continuously.

# COMMAND ----------

smoothTelemetryDF = telemetryDF.groupBy(
  window('enqueuedtime', "10 minutes", "5 minutes"),
  'deviceId'
).agg({'humidity': 'avg'})
display(smoothTelemetryDF)

# COMMAND ----------

# MAGIC %md ## Analyze the telemetry further 
# MAGIC 
# MAGIC To perform more complex analysis, the following cell continuously writes the streaming data to a table in the cluster. The amount of data stored will continue to grow, so in a production system you should periodically delete or archive old telemetry data.
# MAGIC 
# MAGIC ###Write streaming data query results to a database
# MAGIC Writes the final telemetryDF DataFrame to a [database table](https://docs.azuredatabricks.net/user-guide/tables.html) in the cluster. You could choose to write the telemetry to another storage location such as an external database or blob store.
# MAGIC 
# MAGIC For more information, see [Streaming Data Sources and Sinks](https://docs.azuredatabricks.net/spark/latest/structured-streaming/data-sources.html).

# COMMAND ----------

telemetryDF \
    .writeStream \
    .outputMode("append") \
    .format("delta") \
    .option("checkpointLocation", "/delta/events/_checkpoints/etl-from-json") \
    .table("telemetry")

# COMMAND ----------

# MAGIC %md
# MAGIC 
# MAGIC Wait until some streaming data has been written to storage.

# COMMAND ----------

from time import sleep
sleep(60) # wait until some telemtry has been written to storage

# COMMAND ----------

# MAGIC %md
# MAGIC 
# MAGIC ### Generate box plots
# MAGIC The format of the stored data is not suitable for using the Matplotlib [boxplot](https://matplotlib.org/gallery/statistics/boxplot_demo.html) function. It's also not possible to *pivot* streaming data - this is why the previous cell wrote the streaming data to the filesystem.
# MAGIC 
# MAGIC The following code:
# MAGIC 1. Generates a list of device Ids to use as column headings.
# MAGIC 1. Loads and pivots the stored data and then converts it to a pandas [DataFrame](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.html).
# MAGIC 1. Uses Matplotlib to generate a [box plot](https://en.wikipedia.org/wiki/Box_plot)
# MAGIC 
# MAGIC A box plot is a way to show the spread of data and any outliers. The chart shows hourly box plots for each device. You need to wait for some time to see multiple hourly plots.
# MAGIC 
# MAGIC Note: this chart isn't based on streaming data so you need to manually update it by re-running the cell.

# COMMAND ----------

import matplotlib.pyplot as plt

# Get list of distinct deviceId values
devicelist = spark.table('telemetry').select(collect_set('deviceId').alias('deviceId')).first()['deviceId']

# Pivot and convert to a pandas dataframe
pdDF = spark.table('telemetry').groupBy('enqueuedtime').pivot('deviceId').mean('humidity').orderBy('enqueuedtime').withColumn('hour', date_trunc('hour', 'enqueuedtime')).toPandas()

# Use the pandas plotting function
plt.clf()
pdDF.boxplot(column=devicelist, by=['hour'], rot=90, fontsize='medium', layout=(2,2), figsize=(20,8))
display()
