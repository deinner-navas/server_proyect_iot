from datetime import datetime
import pandas as pd
import numpy as np
import os
from sklearn.linear_model import LinearRegression
import time
import pika
import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish

class analitica():
    ventana = 10
    pronostico = 3
    file_name = "data_base.csv"
    servidor = "104.41.140.100" 


    def on_connect(client, userdata, flags, rc):
        print("Connected with result code "+str(rc))
        client.subscribe("$SYS/#")

    def on_message(client, userdata, msg):
        print(msg.topic + " " + str(msg.payload))

    client = mqtt.Client('notificacion_valores') 
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(servidor, 1883, 60)
    client.loop_start()

    def __init__(self) -> None:
        self.load_data()

    def load_data(self):

        if not os.path.isfile(self.file_name):
            self.df = pd.DataFrame(columns=["fecha", "sensor", "valor"])
        else:
            self.df = pd.read_csv (self.file_name)

    def update_data(self, msj):
        msj_vetor = msj.split(",")
        now = datetime.now()
        date_time = now.strftime('%d.%m.%Y %H:%M:%S')
        new_data = {"fecha": date_time, "sensor": msj_vetor[0], "valor": float(msj_vetor[1])}
        self.df = self.df.append(new_data, ignore_index=True)
        new_data = {"fecha": date_time, "sensor": msj_vetor[2], "valor": float(msj_vetor[3])}
        self.df = self.df.append(new_data, ignore_index=True)

        self.publicar("vibracion",msj_vetor[1])
        self.publicar("corriente",msj_vetor[3])

        self.analitica_descriptiva()
        self.analitica_predictiva()
        self.guardar()

    def print_data(self):
        print(self.df)

    def analitica_descriptiva(self):
        self.operaciones("vibracion")
        self.operaciones("corriente")


    def operaciones(self, sensor):
        df_filtrado = self.df[self.df["sensor"] == sensor]
        df_filtrado = df_filtrado["valor"]
        df_filtrado = df_filtrado.tail(self.ventana)
        self.publicar("max-{}".format(sensor), str(df_filtrado.max(skipna = True)))
        self.publicar("min-{}".format(sensor), str(df_filtrado.min(skipna = True)))
        self.publicar("mean-{}".format(sensor), str(df_filtrado.mean(skipna = True)))
        self.publicar("median-{}".format(sensor), str(df_filtrado.median(skipna = True)))
        self.publicar("std-{}".format(sensor), str(df_filtrado.std(skipna = True)))

        if ("max-{}".format(sensor)=="max-vibracion".format(sensor)) and str(df_filtrado.max(skipna = True))>"70":
            publish.single('2/alertavib', "Precaucion vibracion elevada", hostname='104.41.140.100', client_id='notificacion_valores')
            #self.publicar("alerta-vibracion".format(sensor), "Precaucion vibracion Elevada ")

        if ("min-{}".format(sensor)=="min-vibracion".format(sensor)) and str(df_filtrado.min(skipna = True))<"60":
            publish.single('2/alertavib', "Precaucion vibracion baja", hostname='104.41.140.100', client_id='notificacion_valores')
            #self.publicar("alerta-humedad".format(sensor), "Precaucion vibracion Muy Baja")

        if ("max-{}".format(sensor)=="max-corriente".format(sensor)) and str(df_filtrado.max(skipna = True))>"30":
            publish.single('2/alertacor', "Precaucion corriente elevada", hostname='104.41.140.100', client_id='notificacion_valores')
            #self.publicar("alerta-corriente".format(sensor), "Precaucion corriente Elevada ")

        if ("min-{}".format(sensor)=="min-corriente".format(sensor)) and str(df_filtrado.min(skipna = True))<"23":
            publish.single('2/alertacor', "Precaucion corriente baja", hostname='104.41.140.100', client_id='notificacion_valores')
            #self.publicar("alerta-corriente".format(sensor), "Precaucion corriente Muy Baja")


    def analitica_predictiva(self):
        self.regresion("corriente")
        self.regresion("vibracion")


    def regresion(self, sensor):
        df_filtrado = self.df[self.df["sensor"] == sensor]
        df_filtrado = df_filtrado.tail(self.ventana)
        df_filtrado['fecha'] = pd.to_datetime(df_filtrado.pop('fecha'), format='%d.%m.%Y %H:%M:%S')
        df_filtrado['segundos'] = [time.mktime(t.timetuple()) - 18000 for t in df_filtrado['fecha']]
        tiempo = df_filtrado['segundos'].std(skipna = True)
        if np.isnan(tiempo):
            return
        tiempo = int(round(tiempo))
        ultimo_tiempo = df_filtrado['segundos'].iloc[-1]
        ultimo_tiempo = ultimo_tiempo.astype(int)
        range(ultimo_tiempo + tiempo,(self.pronostico + 1) * tiempo + ultimo_tiempo, tiempo)
        nuevos_tiempos = np.array(range(ultimo_tiempo + tiempo,(self.pronostico + 1) * tiempo + ultimo_tiempo, tiempo))

        X = df_filtrado["segundos"].to_numpy().reshape(-1, 1)
        Y = df_filtrado["valor"].to_numpy().reshape(-1, 1)
        linear_regressor = LinearRegression()
        linear_regressor.fit(X, Y)
        Y_pred = linear_regressor.predict(nuevos_tiempos.reshape(-1, 1))
        for tiempo, prediccion in zip(nuevos_tiempos, Y_pred):
            time_format = datetime.utcfromtimestamp(tiempo)
            date_time = time_format.strftime('%d.%m.%Y %H:%M:%S')
            self.publicar("prediccion-{}".format(sensor), "{},{}".format(date_time,prediccion[0]))
            self.publicar("dato_esperado-{}".format(sensor), "{:.2f}".format(prediccion[0]))
    @staticmethod
    def publicar(cola, mensaje):
        connexion = pika.BlockingConnection(pika.ConnectionParameters(host='rabbit'))
        canal = connexion.channel()
        # Declarar la cola
        canal.queue_declare(queue=cola, durable=True)
        # Publicar el mensaje
        canal.basic_publish(exchange='', routing_key=cola, body=mensaje)
        # Cerrar conexi??n
        connexion.close()

    def guardar(self):
        self.df.to_csv(self.file_name, encoding='utf-8')