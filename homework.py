import logging
import os
import sys
import time
from http import HTTPStatus
from pathlib import Path

import requests
import vk_api
from dotenv import load_dotenv
from vk_api.utils import get_random_id

from exceptions import (EnvironmentVariableMissing,
                        HomeworkApiError)

load_dotenv()

SECRETS = ['PRACTICUM_TOKEN', 'VK_TOKEN', 'VK_USER_ID']

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
VK_TOKEN = os.getenv('VK_TOKEN')
VK_USER_ID = os.getenv('VK_USER_ID')
RETRY_PERIOD = 600

ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}
HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

SECRETS_MISSING = 'Секреты {missing_secrets} отсутствуют.'
MESSAGE_SENT = 'Сообщение отправлено: {message}'
MESSAGE_SEND_FAILED = 'Не удалось отправить сообщение: {message}.'
ENDPOINT_UNAVAILABLE = ('Эндпоинт недоступен: {error}. '
                        'Параметры запроса: url={url}, params={params}')
API_STATUS_ERROR = 'Получена ошибка при запросе статуса, код: {status_code}'
API_RESPONSE_ERROR = ('Ошибка: {errors}. '
                      'Параметры запроса: url={url}, params={params}')
RESPONSE_TYPE_ERROR = 'Получен тип {type} вместо словаря.'
HOMEWORKS_KEY_MISSING = 'Ключ `homeworks` отсутствует в ответе.'
CURRENT_DATE_KEY_MISSING = 'Ключ `current_date` отсутствует в ответе.'
CURRENT_DATE_TYPE_ERROR = 'Получен тип {type} вместо числа.'
HOMEWORKS_TYPE_ERROR = 'Ключ `homeworks` имеет тип {type} вместо списка.'
STATUS_CHANGED = 'Изменился статус проверки работы "{name}". {verdict}'
HOMEWORK_NAME_KEY_MISSING = 'Ключ `homework_name` отсутствует в структуре.'
STATUS_KEY_MISSING = 'Ключ `status` отсутствует в структуре.'
NOT_A_STRING_ERROR = 'Получен тип {type} вместо строки.'
BOT_STARTED = 'Бот запущен.'
NO_NEW_STATUSES = 'Новых статусов нет'
PROGRAM_FAILURE = 'Сбой в работе программы: {error}'
ERROR_REPEATED = 'Ошибка повторилась, в VK не отправляю.'

logger = logging.getLogger(__name__)


def init_logger():
    """Настройка логгера."""
    Path("logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - [%(levelname)s] - %(message)s',
        handlers=[
            logging.FileHandler(filename=f'logs/app-{time.strftime(
                "%Y%m%d-%H%M%S")}.log', mode='a', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )


def check_tokens():
    """Проверяет секреты окружения, необходимые для работы программы."""
    missing_secrets = [name for name in SECRETS if not globals()[name]]
    if missing_secrets:
        message = SECRETS_MISSING.format(missing_secrets=missing_secrets)
        logger.critical(message)
        raise EnvironmentVariableMissing(message)


def send_message(vk, message):
    """Отправляет сообщение в VK-чат."""
    try:
        vk.messages.send(
            user_id=VK_USER_ID,
            message=message,
            random_id=get_random_id()
        )
    except Exception:
        logger.exception(MESSAGE_SEND_FAILED.format(message=message))
        return False
    logger.debug(MESSAGE_SENT.format(message=message))
    return True


def get_api_answer(timestamp: int):
    """Делает запрос к единственному эндпоинту API-сервиса домашних работ."""
    payload = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
    except requests.RequestException as error:
        raise ConnectionError(
            ENDPOINT_UNAVAILABLE.format(
                error=error,
                url=ENDPOINT,
                params=payload
            )
        ) from error
    if response.status_code != HTTPStatus.OK:
        raise HomeworkApiError(
            API_STATUS_ERROR.format(status_code=response.status_code)
        )

    data_json = response.json()
    errors = [{x: data_json[x]} for x in ['error', 'code'] if x in data_json]
    if errors:
        raise RuntimeError(
            API_RESPONSE_ERROR.format(
                errors=errors,
                url=ENDPOINT,
                params=payload
            )
        )
    return data_json


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if type(response) is not dict:
        raise TypeError(RESPONSE_TYPE_ERROR.format(type=type(response)))
    if 'homeworks' not in response:
        raise KeyError(HOMEWORKS_KEY_MISSING)
    if 'current_date' not in response:
        raise KeyError(CURRENT_DATE_KEY_MISSING)
    if type(response['current_date']) is not int:
        raise TypeError(CURRENT_DATE_TYPE_ERROR.format(
            type=type(response['current_date']
                      )))
    if type(response['homeworks']) is not list:
        raise TypeError(HOMEWORKS_TYPE_ERROR.format(
            type=type(response['homeworks']
                      )))
    return response


def parse_status(homework):
    """Извлекает статус домашней работы в сообщение."""
    validate_homework(homework)
    homework_status = homework['status']
    if homework_status not in HOMEWORK_VERDICTS:
        raise ValueError(homework_status)
    verdict = HOMEWORK_VERDICTS[homework_status]

    return STATUS_CHANGED.format(
        name=homework['homework_name'],
        verdict=verdict
    )


def validate_homework(homework):
    """Проверяет структуру домашнего задания."""
    if 'homework_name' not in homework:
        raise KeyError(HOMEWORK_NAME_KEY_MISSING)
    if 'status' not in homework:
        raise KeyError(STATUS_KEY_MISSING)
    if type(homework['homework_name']) is not str:
        raise TypeError(NOT_A_STRING_ERROR.format(
            type=type(homework['homework_name']
                      )))
    if type(homework['status']) is not str:
        raise TypeError(NOT_A_STRING_ERROR.format(
            type=type(homework['status']
                      )))


def main():
    """Основная логика работы бота."""
    logger.info(BOT_STARTED)
    check_tokens()

    vk = vk_api.VkApi(token=VK_TOKEN).get_api()
    timestamp = 0
    last_message = None
    while True:
        try:
            response = get_api_answer(timestamp)
            data = check_response(response)
            if not data['homeworks']:
                logger.debug(NO_NEW_STATUSES)
                timestamp = data['current_date']
            else:
                homework = max(
                    data['homeworks'],
                    key=lambda hw: hw['date_updated']
                )
                message = parse_status(homework)
                if message == last_message or send_message(vk, message):
                    last_message = message
                    timestamp = data['current_date']
        except Exception as error:
            message = PROGRAM_FAILURE.format(error=error)
            logger.error(message)
            if message == last_message:
                logger.warning(ERROR_REPEATED)
            elif send_message(vk, message):
                last_message = message
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    init_logger()
    main()
