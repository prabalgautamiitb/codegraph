from service import store as imported_store
from service import OrderService


def place_order(order):
    def submit(callback):
        return callback(order)

    svc = OrderService()
    submit(imported_store)
    return svc.submit(order)
