# Test File


class MyClass:
    def __init__(self, value: str):
        self.value = value

    def my_method(self) -> str:
        return self.value


def my_function(x: int) -> int:
    return x * 2


CONSTANT = 42


class AnotherClass:
    def another_method(self) -> str | None:
        return None
