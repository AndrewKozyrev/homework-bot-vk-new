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
MESSAGE_SEND_FAILED = ('Не удалось отправить сообщение: {message}. '
                       'Ошибка: {error}')
ENDPOINT_UNAVAILABLE = ('Эндпоинт недоступен: {error}. Параметры запроса: '
                        'url={url}, headers={headers}, params={params}')
API_STATUS_ERROR = ('Код ответа API: {status_code}. Параметры запроса: '
                    'url={url}, headers={headers}, params={params}')
API_RESPONSE_ERROR = ('Ошибка: {errors}. Параметры запроса: '
                      'url={url}, headers={headers}, params={params}')
RESPONSE_TYPE_ERROR = 'Получен тип {type} вместо словаря.'
HOMEWORKS_KEY_MISSING = 'Ключ `homeworks` отсутствует в ответе.'
HOMEWORKS_TYPE_ERROR = 'Ключ `homeworks` имеет тип {type} вместо списка.'
STATUS_CHANGED = 'Изменился статус проверки работы "{name}". {verdict}'
HOMEWORK_NAME_KEY_MISSING = 'Ключ `homework_name` отсутствует в структуре.'
STATUS_KEY_MISSING = 'Ключ `status` отсутствует в структуре.'
BOT_STARTED = 'Бот запущен.'
NO_NEW_STATUSES = 'Новых статусов нет'
PROGRAM_FAILURE = 'Сбой в работе программы: {error}'
ERROR_REPEATED = 'Ошибка повторилась, в VK не отправляю.'
UNEXPECTED_STATUS = 'Неожиданный статус домашней работы "{name}": {status}'

logger = logging.getLogger(__name__)


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
    except Exception as error:
        logger.exception(MESSAGE_SEND_FAILED.format(
            message=message,
            error=error
        ))
        return False
    logger.debug(MESSAGE_SENT.format(message=message))
    return True


def get_api_answer(timestamp: int):
    """Делает запрос к единственному эндпоинту API-сервиса домашних работ."""
    request_params = dict(url=ENDPOINT, headers=HEADERS,
                          params={'from_date': timestamp})
    try:
        response = requests.get(**request_params)
    except requests.RequestException as error:
        raise ConnectionError(
            ENDPOINT_UNAVAILABLE.format(error=error, **request_params)
        ) from error
    if response.status_code != HTTPStatus.OK:
        raise HomeworkApiError(API_STATUS_ERROR.format(
            status_code=response.status_code,
            **request_params
        ))

    data_json = response.json()
    errors = [{x: data_json[x]} for x in ['error', 'code'] if x in data_json]
    if errors:
        raise RuntimeError(
            API_RESPONSE_ERROR.format(
                errors=errors,
                **request_params
            )
        )
    return data_json


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if type(response) is not dict:
        raise TypeError(RESPONSE_TYPE_ERROR.format(type=type(response)))
    if 'homeworks' not in response:
        raise KeyError(HOMEWORKS_KEY_MISSING)
    homeworks = response['homeworks']
    if type(homeworks) is not list:
        raise TypeError(HOMEWORKS_TYPE_ERROR.format(type=type(homeworks)))
    return homeworks


def parse_status(homework):
    """Извлекает статус домашней работы в сообщение."""
    if 'homework_name' not in homework:
        raise KeyError(HOMEWORK_NAME_KEY_MISSING)
    if 'status' not in homework:
        raise KeyError(STATUS_KEY_MISSING)
    homework_status = homework['status']
    if homework_status not in HOMEWORK_VERDICTS:
        raise ValueError(UNEXPECTED_STATUS.format(
            name=homework.get('homework_name'), status=homework_status))

    return STATUS_CHANGED.format(
        name=homework['homework_name'],
        verdict=HOMEWORK_VERDICTS[homework_status]
    )


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
            homeworks = check_response(response)
            if homeworks:
                message = parse_status(homeworks[0])
                if message == last_message or send_message(vk, message):
                    last_message = message
                    timestamp = response.get('current_date', timestamp)
            else:
                logger.debug(NO_NEW_STATUSES)
        except Exception as error:
            message = PROGRAM_FAILURE.format(error=error)
            logger.error(message)
            if message == last_message:
                logger.warning(ERROR_REPEATED)
            elif send_message(vk, message):
                last_message = message
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
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
    main()
