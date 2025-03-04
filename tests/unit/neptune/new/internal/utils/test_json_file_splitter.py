#
# Copyright (c) 2020, Neptune Labs Sp. z o.o.
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
import unittest

from neptune.new.internal.utils.json_file_splitter import JsonFileSplitter
from tests.unit.neptune.new.utils.file_helpers import create_file


class TestJsonFileSplitter(unittest.TestCase):
    def test_simple_file(self):
        content = """
{
    "a": 5,
    "b": "text"
}
{
    "a": 13
}
{}
""".lstrip()

        with create_file(content) as filename:
            splitter = JsonFileSplitter(filename)
            self.assertEqual(splitter.get(), {"a": 5, "b": "text"})
            self.assertEqual(splitter.get(), {"a": 13})
            self.assertEqual(splitter.get(), {})
            self.assertEqual(splitter.get(), None)
            splitter.close()

    def test_append(self):
        content1 = """
            {
                "a": 5,
                "b": "text"
            }
            {
                "a": 13
            }"""

        content2 = """
            {
                "q": 555,
                "r": "something"
            }
            {
                "a": {
                    "b": [1, 2, 3]
                }
            }
            {}"""

        with create_file(content1) as filename, open(filename, "a") as fp:
            splitter = JsonFileSplitter(filename)
            self.assertEqual(splitter.get(), {"a": 5, "b": "text"})
            self.assertEqual(splitter.get(), {"a": 13})
            self.assertEqual(splitter.get(), None)
            fp.write(content2)
            fp.flush()
            self.assertEqual(splitter.get(), {"q": 555, "r": "something"})
            self.assertEqual(splitter.get(), {"a": {"b": [1, 2, 3]}})
            self.assertEqual(splitter.get(), {})
            self.assertEqual(splitter.get(), None)
            splitter.close()

    def test_append_cut_json(self):
        content1 = """
            {
                "a": 5,
                "b": "text"
            }
            {
                "a": 1"""

        content2 = """55,
                "r": "something"
            }
            {
                "a": {
                    "b": [1, 2, 3]
                }
            }"""

        with create_file(content1) as filename, open(filename, "a") as fp:
            splitter = JsonFileSplitter(filename)
            self.assertEqual(splitter.get(), {"a": 5, "b": "text"})
            self.assertEqual(splitter.get(), None)
            fp.write(content2)
            fp.flush()
            self.assertEqual(splitter.get(), {"a": 155, "r": "something"})
            self.assertEqual(splitter.get(), {"a": {"b": [1, 2, 3]}})
            self.assertEqual(splitter.get(), None)
            splitter.close()

    def test_big_json(self):
        content = """
{
    "a": 5,
    "b": "text"
}
{
    "a": "%s",
    "b": "%s"
}
{}
""".lstrip() % (
            "x" * JsonFileSplitter.BUFFER_SIZE * 2,
            "y" * JsonFileSplitter.BUFFER_SIZE * 2,
        )

        with create_file(content) as filename:
            splitter = JsonFileSplitter(filename)
            self.assertEqual(splitter.get(), {"a": 5, "b": "text"})
            self.assertEqual(
                splitter.get(),
                {
                    "a": "x" * JsonFileSplitter.BUFFER_SIZE * 2,
                    "b": "y" * JsonFileSplitter.BUFFER_SIZE * 2,
                },
            )
            self.assertEqual(splitter.get(), {})
            self.assertEqual(splitter.get(), None)
            splitter.close()

    def test_data_size(self):
        object1 = """{
                "a": 5,
                "b": "text"
            }"""
        object2 = """{
                "a": 155,
                "r": "something"
            }"""
        object3 = """{
                "a": {
                    "b": [1, 2, 3]
                }
            }"""
        content1 = """
            {
                "a": 5,
                "b": "text"
            }
            {
                "a": 1"""

        content2 = """55,
                "r": "something"
            }
            {
                "a": {
                    "b": [1, 2, 3]
                }
            }"""

        with create_file(content1) as filename, open(filename, "a") as fp:
            splitter = JsonFileSplitter(filename)
            self.assertEqual(splitter.get_with_size(), ({"a": 5, "b": "text"}, len(object1)))
            self.assertIsNone(splitter.get_with_size()[0])
            fp.write(content2)
            fp.flush()
            self.assertEqual(splitter.get_with_size(), ({"a": 155, "r": "something"}, len(object2)))
            self.assertEqual(splitter.get_with_size(), ({"a": {"b": [1, 2, 3]}}, len(object3)))
            self.assertIsNone(splitter.get_with_size()[0])
            splitter.close()
