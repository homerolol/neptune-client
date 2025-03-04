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
import json
import os
import re
from pathlib import Path

import pytest
from click.testing import CliRunner

import neptune.new as neptune
from neptune.common.exceptions import NeptuneException
from neptune.new.cli import sync
from src.neptune.new.cli.commands import clear
from tests.e2e.base import (
    AVAILABLE_CONTAINERS,
    BaseE2ETest,
    fake,
)
from tests.e2e.utils import (
    DISABLE_SYSLOG_KWARGS,
    initialize_container,
    reinitialize_container,
    tmp_context,
)

runner = CliRunner()


class TestSync(BaseE2ETest):
    SYNCHRONIZED_SYSID_RE = r"[\w-]+/[\w-]+/([\w-]+)"

    @pytest.mark.parametrize("container_type", AVAILABLE_CONTAINERS)
    def test_sync_container(self, container_type, environment):
        with tmp_context() as tmp:
            key = self.gen_key()
            original_value = fake.unique.word()
            updated_value = fake.unique.word()

            with initialize_container(container_type=container_type, project=environment.project) as container:
                # assign original value
                container[key] = original_value
                container.wait()
                container_id = container._id
                container_sys_id = container._sys_id

                self.stop_synchronization_process(container)
                # add random property - the queue will not be empty on close
                container[self.gen_key()] = fake.unique.word()

            # manually add operations to queue
            queue_dir = list(Path(f"./.neptune/async/{container_type}__{container_id}/").glob("exec-*"))[0]
            with open(queue_dir / "last_put_version", encoding="utf-8") as last_put_version_f:
                last_put_version = int(last_put_version_f.read())
            with open(queue_dir / "data-1.log", "a", encoding="utf-8") as queue_f:
                queue_f.write(
                    json.dumps(
                        {
                            "obj": {
                                "type": "AssignString",
                                "path": key.split("/"),
                                "value": updated_value,
                            },
                            "version": last_put_version + 1,
                        }
                    )
                )
                queue_f.write(
                    json.dumps(
                        {
                            "obj": {
                                "type": "CopyAttribute",
                                "path": ["copy"] + key.split("/"),
                                "container_id": container_id,
                                "container_type": container_type,
                                "source_path": key.split("/"),
                                "source_attr_name": "String",
                            },
                            "version": last_put_version + 2,
                        }
                    )
                )
            with open(queue_dir / "last_put_version", "w", encoding="utf-8") as last_put_version_f:
                last_put_version_f.write(str(last_put_version + 2))

            with reinitialize_container(
                container_sys_id, container_type, project=environment.project, mode="read-only"
            ) as container:
                # server should have the original value
                assert container[key].fetch() == original_value

            # run neptune sync
            result = runner.invoke(sync, ["--path", tmp])
            assert result.exit_code == 0

            with reinitialize_container(container_sys_id, container_type, project=environment.project) as container:
                # and we should get the updated value from server
                assert container[key].fetch() == updated_value
                assert container["copy/" + key].fetch() == updated_value

    @staticmethod
    def stop_synchronization_process(container):
        container._op_processor._consumer.interrupt()

    def test_offline_sync(self, environment):
        with tmp_context() as tmp:
            # create run in offline mode
            run = neptune.init_run(
                mode="offline",
                project=environment.project,
                **DISABLE_SYSLOG_KWARGS,
            )
            # assign some values
            key = self.gen_key()
            val = fake.word()
            run[key] = val

            # and stop it
            run.stop()

            # run asynchronously
            result = runner.invoke(sync, ["--path", tmp, "-p", environment.project])
            assert result.exit_code == 0

            # we'll have to parse sync output to determine short_id
            sys_id_found = re.search(self.SYNCHRONIZED_SYSID_RE, result.stdout)
            assert len(sys_id_found.groups()) == 1
            sys_id = sys_id_found.group(1)

            run2 = neptune.init_run(with_id=sys_id, project=environment.project)
            assert run2[key].fetch() == val
            run2.stop()

    @pytest.mark.parametrize("container_type", ["run"])
    def test_clear_command_offline_and_online_containers(self, environment, container_type):
        with tmp_context() as tmp:
            key = self.gen_key()

            with initialize_container(container_type=container_type, project=environment.project) as container:
                self.stop_synchronization_process(container)

                container[key] = fake.unique.word()
                container_path = container._op_processor._queue._dir_path
                container_sys_id = container._sys_id

            with initialize_container(
                container_type=container_type, project=environment.project, mode="offline"
            ) as container:
                container[key] = fake.unique.word()
                offline_container_path = container._op_processor._queue._dir_path
                offline_container_id = container._id

            assert os.path.exists(container_path)
            assert os.path.exists(offline_container_path)

            result = runner.invoke(clear, args=["--path", tmp], input="y")

            assert result.exit_code == 0

            assert not os.path.exists(container_path)
            assert not os.path.exists(offline_container_path)
            assert result.output.splitlines() == [
                "",
                "Unsynchronized objects:",
                f"- {environment.project}/{container_sys_id}",
                "",
                "Unsynchronized offline objects:",
                f"- offline/run__{offline_container_id}",
                "",
                "Do you want to delete the listed metadata? [y/N]: y",
                f"Deleted: {offline_container_path}",
                f"Deleted: {container_path.parent}",
            ]

    @pytest.mark.parametrize("container_type", AVAILABLE_CONTAINERS)
    def test_clear_command_online_containers(self, environment, container_type):
        with tmp_context() as tmp:
            key = self.gen_key()

            with initialize_container(container_type=container_type, project=environment.project) as container:
                self.stop_synchronization_process(container)

                container[key] = fake.unique.word()
                container_path = container._op_processor._queue._dir_path
                container_sys_id = container._sys_id

            assert os.path.exists(container_path)

            result = runner.invoke(clear, args=["--path", tmp], input="y")
            assert result.exit_code == 0

            assert not os.path.exists(container_path)
            assert result.output.splitlines() == [
                "",
                "Unsynchronized objects:",
                f"- {environment.project}/{container_sys_id}",
                "",
                "Do you want to delete the listed metadata? [y/N]: y",
                f"Deleted: {container_path.parent}",
            ]

    @pytest.mark.parametrize("container_type", AVAILABLE_CONTAINERS)
    def test_sync_should_delete_directories(self, environment, container_type):
        with tmp_context() as tmp:
            key = self.gen_key()

            with initialize_container(container_type=container_type, project=environment.project) as container:
                self.stop_synchronization_process(container)

                container[key] = fake.unique.word()
                container_path = container._op_processor._queue._dir_path

            assert os.path.exists(container_path)

            result = runner.invoke(sync, args=["--path", tmp])
            assert result.exit_code == 0

            assert not os.path.exists(container_path)

    @pytest.mark.parametrize("container_type", ["model", "model_version", "project"])
    def test_cannot_offline_non_runs(self, environment, container_type):
        with pytest.raises(NeptuneException) as e:
            initialize_container(
                container_type=container_type,
                project=environment.project,
                mode="offline",
            )
        assert "can't be initialized in OFFLINE mode" in str(e.value)
