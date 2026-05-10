import uuid

from common.logging import bind_request_id, reset_request_id


class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)
        request_id_token = bind_request_id(request.request_id)
        try:
            response = self.get_response(request)
        finally:
            reset_request_id(request_id_token)
        response["X-Request-ID"] = request.request_id
        return response
