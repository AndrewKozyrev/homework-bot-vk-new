class EnvironmentVariableMissing(Exception):
    def __init__(self, message):
        super().__init__(message)


class HomeworkApiError(Exception):
    def __init__(self, message):
        super().__init__(message)
