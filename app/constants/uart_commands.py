class UARTCommand:
    # Connection
    PING = "PING"

    # Kickboard Control
    LOCK = "LOCK"
    UNLOCK = "UNLOCK"

    # Sensor Request
    REQUEST_MQ3 = "REQ:MQ3"
    REQUEST_WEIGHT = "REQ:WEIGHT"
    REQUEST_FACE = "REQ:FACE"

    # Status Request
    REQUEST_STATUS = "REQ:STATUS"