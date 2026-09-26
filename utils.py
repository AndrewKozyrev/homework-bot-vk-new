from pydantic import BaseModel


class Homework(BaseModel):
    status: str
    homework_name: str


class HomeworkStatus(BaseModel):
    homeworks: list[Homework]
    current_date: int
