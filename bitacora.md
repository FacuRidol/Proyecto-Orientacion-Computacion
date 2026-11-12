Primera Clase

    Este dia se definio de que trataria el proyecto y se presento una idea en formato escrito y de forma formal.

Segundo Clase

    Creamos el entorno virtual dentro de la raspberry e instalamos las librerias necesarias para el correcto funcionameinto de los pines, la instlacion de python, instalacion de flask etc.
    Comenzamos a desrrollar el index de forma basica y a testear el funcionamiento de la raspy con los pines GPIO, probamos como activar o desactivar las señales de los pines a traves de la web.
    Comenzamos haciendo funcionar las leds de forma manual con botones dentro de la web.

Tercera Clase

    Conectamos el servo y testeamos de manera manual dentro de la pagina el funcionamiento de este y la correcta interpretacion de la raspy.
    Comenzamos las pruebas con los comandos de voz, al hacer esto nos percatamos que dependiendo del navegar ciertas funciones dentro de javascript no funcionarian de forma satisfactoria y por ende tuvimos que replantear la forma de interpretacion del audio. Entre muchas alternativas nos decidimos por instalar un modelo de interpretacionde audio (Vosk) que se ejecute de forma local en la raspy para no depender de la conexion a internet.
    En el proceso anterior cambiamos la forma de comunicacion dentro del proyecto, ahora el audio es capturado por JavaScript y enviado directamente a Vosk, este "Traduce el audio" a un formato valido para que el resto de la pagina interprete la señal y actue en consecuencia.
    La necesidad de capturar el audio por medio de la web genero el conflicto de que los navegadores no permitian dar acceso a el microfono a causa de la falta de una certificacion https. Esto nos obligo a crear un certificado con calves pem validas que permita dar acceso al microfono.
    Finalmente pudimos hacer funcionar los comandos de voz basicos de encender o apagar las leds pero no con el servo.

Cuarta Clase

    Cambiamos la forma de activacion de los comandos de voz haciendo necesario que antes de decirlos sea necesaria la palabra comando por ejemplo "comando encender LED uno". Ademas, cambiamos la palabra de "servo" por "giro" debido a que Vosk no reconocia correctamente la primera y para finalizar el comando pusimos como palabra fianl "grados", de esta forma logramos hacer funcionar comandos tales como "giro a 45 grados"
    Investigamos como conectar el sensor ultrasonico sin el incoveniente de los voltages desiguales. Llegamos a la conclusion que el metodo mas economico y sencillo seria utilizar dos resistencias, una de 1000 ohms y otra de 1500 o 2000 omhs. 
    Empezamos a mejorar la interfaz de la pagina agregando indicadores visuales, una estructura clara para diferenciar las secciones de cada elemento dentro de la web.

Quinta Clase

    Conectamos el sensor ultrasonico con lasresistencias pertinentes para su correcto funcionamiento.
    Comprobamos que las mediciones se interpreten correctamente en la pagina y esta actualice constantemente para mostrar el nuevo valor.
    Ahora la pagina comprobara una vez por segundo el estado de todos los dispositivos, esto es debido a que antes no cooncordaba el estado de cada dispositivo con el verdareo debdio a que otra sesion podia modificarlo.

Sexta Clase

