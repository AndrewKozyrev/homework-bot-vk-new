import logging
import os
import random
import sys
import time

import requests
import vk_api
from dotenv import load_dotenv
from pydantic import ValidationError

from exceptions import (EnvironmentVariableMissing,
                        HomeworkApiError,
                        InvalidHomeworkStatus)
from utils import HomeworkStatus, Homework

load_dotenv()


def init_logger():
    """Настройка логгера."""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s - [%(levelname)s] - %(message)s'
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


logger = init_logger()

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


def check_tokens():
    """Проверяет секреты окружения, необходимые для работы программы."""
    secrets = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'VK_TOKEN': VK_TOKEN,
        'VK_USER_ID': VK_USER_ID
    }
    missing_secrets = [name for (name, value) in secrets.items() if not value]
    if missing_secrets:
        message = f'Секреты {', '.join(missing_secrets)} отсутствуют.'
        logger.critical(message)
        raise EnvironmentVariableMissing(message)


def send_message(vk, message):
    """Отправляет сообщение в VK-чат."""
    try:
        vk.messages.send(
            user_id=VK_USER_ID,
            message=message,
            random_id=random.randint(1, 100000)
        )
        logger.debug(f'Сообщение отправлено: {message}')
    except Exception as error:
        logger.error(f'Не удалось отправить сообщение в VK: {error}')


def get_api_answer(timestamp: int):
    """Делает запрос к единственному эндпоинту API-сервиса домашних работ."""
    payload = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
    except requests.RequestException as error:
        raise HomeworkApiError(f'Эндпоинт недоступен: {error}') from error
    if response.status_code == 200:
        return response.json()
    else:
        raise HomeworkApiError(
            f'Получена ошибка при запросе статуса, код: {response.status_code}'
        )


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    try:
        return HomeworkStatus.model_validate(response)
    except ValidationError as error:
        raise TypeError(error)


def parse_status(arg):
    """Извлекает статус домашней работы в сообщение."""
    homework = Homework.model_validate(arg)
    verdict = HOMEWORK_VERDICTS.get(homework.status)
    if not verdict:
        raise InvalidHomeworkStatus(homework.status)

    return (f'Изменился статус проверки работы '
            f'"{homework.homework_name}". {verdict}')


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
            homework_status = check_response(response)
            if not homework_status.homeworks:
                logger.debug('Новых статусов нет')
            else:
                message = parse_status(homework_status.homeworks[-1])
                send_message(vk, message)
            timestamp = homework_status.current_date
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
    main()
