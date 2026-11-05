from datetime import datetime

import requests
from airflow import DAG
from airflow.operators.python import PythonOperator

CONFIG = requests.get("https://config.internal/orders").json()


def export_orders():
    print("exporting", CONFIG["table"])


with DAG("orders_export", start_date=datetime(2026, 1, 1), schedule="@daily") as dag:
    PythonOperator(task_id="export", python_callable=export_orders)
