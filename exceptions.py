class EnvironmentVariableMissing(Exception):
    def __init__(self, message):
        super().__init__(message)


class HomeworkApiError(Exception):
    def __init__(self, message):
        super().__init__(message)


class InvalidHomeworkStatus(Exception):
    def __init__(self, status):
        super().__init__(f'Неожиданный статус домашней работы: {status}')
