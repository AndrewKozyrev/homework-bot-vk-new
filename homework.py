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
logger = logging.getLogger(__name__)


def check_tokens():
    """Проверяет секреты окружения, необходимые для работы программы."""
    missing_secrets = [name for name in SECRETS if not globals()[name]]
    if missing_secrets:
        message = f'Секреты {missing_secrets} отсутствуют.'
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
        logger.debug(f'Сообщение отправлено: {message}')
    except Exception:
        logger.exception(f'Не удалось отправить сообщение: {message}.')


def get_api_answer(timestamp: int):
    """Делает запрос к единственному эндпоинту API-сервиса домашних работ."""
    payload = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
    except requests.RequestException as error:
        raise ConnectionError(
            f'Эндпоинт недоступен: {error}. '
            f'Параметры запроса: url={ENDPOINT}, params={payload}'
        ) from error
    if response.status_code != HTTPStatus.OK:
        raise HomeworkApiError(
            f'Получена ошибка при запросе статуса, код: {response.status_code}'
        )

    data_json = response.json()
    errors = [{x: data_json[x]} for x in ['error', 'code'] if x in data_json]
    if errors:
        raise RuntimeError(
            f'Ошибка: {errors}. '
            f'Параметры запроса: url={ENDPOINT}, params={payload}'
        )
    return data_json


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if type(response) is not dict:
        raise TypeError(f'Получен тип {type(response)} вместо словаря.')
    if 'homeworks' not in response:
        raise KeyError('Ключ `homeworks` отсутствует в ответе.')
    if 'current_date' not in response:
        raise KeyError('Ключ `current_date` отсутствует в ответе.')
    if type(response['current_date']) is not int:
        raise TypeError(
            f'Получен тип {type(response['current_date'])} вместо числа.'
        )
    if type(response['homeworks']) is not list:
        raise TypeError(
            f'Ключ `homeworks` имеет тип '
            f'{type(response['homeworks'])} вместо списка.'
        )
    return response


def parse_status(homework):
    """Извлекает статус домашней работы в сообщение."""
    validate_homework(homework)
    homework_status = homework['status']
    if homework_status not in HOMEWORK_VERDICTS:
        raise ValueError(homework_status)
    verdict = HOMEWORK_VERDICTS[homework_status]

    return (f'Изменился статус проверки работы '
            f'"{homework['homework_name']}". {verdict}')


def validate_homework(homework):
    """Проверяет структуру домашнего задания."""
    if 'homework_name' not in homework:
        raise KeyError('Ключ `homework_name` отсутствует в структуре.')
    if 'status' not in homework:
        raise KeyError('Ключ `status` отсутствует в структуре.')
    if type(homework['homework_name']) is not str:
        raise TypeError(
            f'Получен тип {type(homework['homework_name'])} вместо строки.'
        )
    if type(homework['status']) is not str:
        raise TypeError(
            f'Получен тип {type(homework['status'])} вместо строки.'
        )


def main():
    """Основная логика работы бота."""
    logger.info('Бот запущен.')
    check_tokens()

    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    timestamp = 0
    last_error = None
    while True:
        try:
            response = get_api_answer(timestamp)
            data = check_response(response)
            if not data['homeworks']:
                logger.debug('Новых статусов нет')
            else:
                message = parse_status(data['homeworks'][-1])
                send_message(vk, message)
            timestamp = data['current_date']
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if last_error and type(error) is type(last_error):
                logger.warning('Ошибка повторилась, в VK не отправляю.')
            else:
                send_message(vk, message)
                last_error = error
        else:
            last_error = None
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    init_logger()
    main()
