import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parents[1] / "bloomsmart"))

from models.user import UserModel
from repository.user import UserRepository


class FakeTable:
    def __init__(self):
        self.items = {}
        self.put_calls = 0

    def put_item(self, Item):
        self.put_calls += 1
        self.items[Item["user_id"]] = Item

    def get_item(self, Key):
        return {"Item": self.items.get(Key["user_id"])}

    def scan(self, **kwargs):
        return {"Items": list(self.items.values())}

    def update_item(self, **kwargs):
        values = kwargs["ExpressionAttributeValues"]
        names = kwargs["ExpressionAttributeNames"]
        key = kwargs["Key"]["user_id"]
        self.items[key].update({names[name]: value for name, value in ((name, value) for name, value in values.items())})


class FakeResource:
    def __init__(self):
        self.fake_table = FakeTable()

    def Table(self, _name):
        return self.fake_table


def test_user_save_and_read_are_pydantic_models():
    resource = FakeResource()
    repository = UserRepository(dynamodb_resource=resource)
    user = UserModel(user_id="u1", username="demo", password_hash="hash")

    assert repository.save(user)
    loaded = repository.get_by_id("u1")

    assert isinstance(loaded, UserModel)
    assert loaded.user_id == "u1"


def test_invalid_user_is_rejected_before_dynamo_write():
    resource = FakeResource()
    repository = UserRepository(dynamodb_resource=resource)

    with pytest.raises(ValidationError):
        repository.save({"user_id": "u1", "username": "demo"})

    assert resource.fake_table.put_calls == 0


def test_update_revalidates_merged_user_before_write():
    resource = FakeResource()
    repository = UserRepository(dynamodb_resource=resource)
    repository.save(UserModel(user_id="u1", username="demo", password_hash="hash"))

    with pytest.raises(ValidationError):
        repository.update_google_credentials("u1", "", clear_password=True)
