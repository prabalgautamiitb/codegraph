class BaseService:
    def audit(self, message):
        return message


class OrderService(BaseService):
    def submit(self, order):
        validate(order)
        return store(order)


def validate(order):
    return bool(order)


def store(order):
    # Unicode in source should not break byte spans: café
    return {"ok": True, "order": order}
