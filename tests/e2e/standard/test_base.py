#
# Copyright (c) 2021, Neptune Labs Sp. z o.o.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import random
from datetime import (
    datetime,
    timezone,
)

import pytest

from neptune.new.metadata_containers import MetadataContainer
from tests.e2e.base import (
    AVAILABLE_CONTAINERS,
    BaseE2ETest,
    fake,
)


class TestAtoms(BaseE2ETest):
    @pytest.mark.parametrize("container", AVAILABLE_CONTAINERS, indirect=True)
    @pytest.mark.parametrize("value", [random.randint(0, 100), random.random(), fake.boolean(), fake.word()])
    def test_simple_assign_and_fetch(self, container: MetadataContainer, value):
        key = self.gen_key()

        container[key] = value
        container.sync()
        assert container[key].fetch() == value

    @pytest.mark.parametrize("container", AVAILABLE_CONTAINERS, indirect=True)
    def test_simple_assign_datetime(self, container: MetadataContainer):
        key = self.gen_key()
        now = datetime.now()

        container[key] = now
        container.sync()

        # expect truncate to milliseconds and add UTC timezone
        expected_now = now.astimezone(timezone.utc).replace(microsecond=int(now.microsecond / 1000) * 1000)
        assert container[key].fetch() == expected_now

    @pytest.mark.parametrize("container", AVAILABLE_CONTAINERS, indirect=True)
    def test_fetch_non_existing_key(self, container: MetadataContainer):
        key = self.gen_key()
        with pytest.raises(AttributeError):
            container[key].fetch()

    @pytest.mark.parametrize("container", AVAILABLE_CONTAINERS, indirect=True)
    def test_delete_atom(self, container: MetadataContainer):
        key = self.gen_key()
        value = fake.name()

        container[key] = value
        container.sync()

        assert container[key].fetch() == value

        del container[key]
        with pytest.raises(AttributeError):
            container[key].fetch()


class TestNamespace(BaseE2ETest):
    @pytest.mark.parametrize("container", AVAILABLE_CONTAINERS, indirect=True)
    def test_reassigning(self, container: MetadataContainer):
        namespace = self.gen_key()
        key = f"{fake.unique.word()}/{fake.unique.word()}"
        value = fake.name()

        # Assign a namespace
        container[namespace] = {f"{key}": value}
        container.sync()

        assert container[f"{namespace}/{key}"].fetch() == value

        # Direct reassign internal value
        value = fake.name()
        container[f"{namespace}/{key}"] = value
        container.sync()

        assert container[f"{namespace}/{key}"].fetch() == value

        # Reassigning by namespace
        value = fake.name()
        container[namespace] = {f"{key}": value}
        container.sync()

        assert container[f"{namespace}/{key}"].fetch() == value

    @pytest.mark.parametrize("container", AVAILABLE_CONTAINERS, indirect=True)
    def test_distinct_types(self, container: MetadataContainer):
        namespace = self.gen_key()
        key = f"{fake.unique.word()}/{fake.unique.word()}"
        value = random.randint(0, 100)

        container[namespace] = {f"{key}": value}
        container.sync()

        assert container[f"{namespace}/{key}"].fetch() == value

        new_value = fake.name()

        with pytest.raises(ValueError):
            container[namespace] = {f"{key}": new_value}
            container.sync()

    @pytest.mark.parametrize("container", AVAILABLE_CONTAINERS, indirect=True)
    def test_delete_namespace(self, container: MetadataContainer):
        namespace = fake.unique.word()
        key1 = fake.unique.word()
        key2 = fake.unique.word()
        value1 = fake.name()
        value2 = fake.name()

        container[namespace][key1] = value1
        container[namespace][key2] = value2
        container.sync()

        assert container[namespace][key1].fetch() == value1
        assert container[namespace][key2].fetch() == value2

        del container[namespace]
        with pytest.raises(AttributeError):
            container[namespace][key1].fetch()
        with pytest.raises(AttributeError):
            container[namespace][key2].fetch()


class TestStringSet(BaseE2ETest):
    neptune_tags_path = "sys/tags"

    @pytest.mark.parametrize("container", AVAILABLE_CONTAINERS, indirect=True)
    def test_do_not_accept_non_tag_path(self, container: MetadataContainer):
        random_path = "some/path"
        container[random_path].add(fake.unique.word())
        container.sync()

        with pytest.raises(AttributeError):
            # backends accepts `'sys/tags'` only
            container[random_path].fetch()

    @pytest.mark.parametrize("container", AVAILABLE_CONTAINERS, indirect=True)
    def test_add_and_remove_tags(self, container: MetadataContainer):
        remaining_tag1 = fake.unique.word()
        remaining_tag2 = fake.unique.word()
        to_remove_tag1 = fake.unique.word()
        to_remove_tag2 = fake.unique.word()

        container.sync()
        if container.exists(self.neptune_tags_path):
            container[self.neptune_tags_path].clear()
        container[self.neptune_tags_path].add(remaining_tag1)
        container[self.neptune_tags_path].add([to_remove_tag1, remaining_tag2])
        container[self.neptune_tags_path].remove(to_remove_tag1)
        container[self.neptune_tags_path].remove(to_remove_tag2)  # remove non existing tag
        container.sync()

        assert container[self.neptune_tags_path].fetch() == {
            remaining_tag1,
            remaining_tag2,
        }
