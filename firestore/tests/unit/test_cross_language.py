# Copyright 2017 Google LLC All rights reserved.
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

import functools
import glob
import json

import mock
import pytest

from google.protobuf import text_format
from google.cloud.firestore_v1beta1.proto import firestore_pb2
from google.cloud.firestore_v1beta1.proto import test_pb2
from google.cloud.firestore_v1beta1.proto import write_pb2


def _load_testproto(filename):

    with open(filename, 'r') as tp_file:
        tp_text = tp_file.read()
    test_proto = test_pb2.Test()
    text_format.Merge(tp_text, test_proto)
    return test_proto


_ALL_TESTPROTOS = [
    _load_testproto(filename) for filename in sorted(
        glob.glob('tests/unit/testdata/*.textproto'))]

_CREATE_TESTPROTOS = [
    test_proto for test_proto in _ALL_TESTPROTOS
    if test_proto.WhichOneof('test') == 'create']

_GET_TESTPROTOS = [
    test_proto for test_proto in _ALL_TESTPROTOS
    if test_proto.WhichOneof('test') == 'get']

_SET_TESTPROTOS = [
    test_proto for test_proto in _ALL_TESTPROTOS
    if test_proto.WhichOneof('test') == 'set']

_UPDATE_TESTPROTOS = [
    test_proto for test_proto in _ALL_TESTPROTOS
    if test_proto.WhichOneof('test') == 'update']

_UPDATE_PATHS_TESTPROTOS = [
    test_proto for test_proto in _ALL_TESTPROTOS
    if test_proto.WhichOneof('test') == 'update_paths']

_DELETE_TESTPROTOS = [
    test_proto for test_proto in _ALL_TESTPROTOS
    if test_proto.WhichOneof('test') == 'delete']

_LISTEN_TESTPROTOS = [
    test_proto for test_proto in _ALL_TESTPROTOS
    if test_proto.WhichOneof('test') == 'listen']


def _mock_firestore_api():
    firestore_api = mock.Mock(spec=['commit'])
    commit_response = firestore_pb2.CommitResponse(
        write_results=[write_pb2.WriteResult()],
    )
    firestore_api.commit.return_value = commit_response
    return firestore_api


def _make_client_document(firestore_api, testcase):
    from google.cloud.firestore_v1beta1 import Client
    from google.cloud.firestore_v1beta1.client import DEFAULT_DATABASE
    import google.auth.credentials

    _, project, _, database, _, doc_path = testcase.doc_ref_path.split('/', 5)
    assert database == DEFAULT_DATABASE

    # Attach the fake GAPIC to a real client.
    credentials = mock.Mock(spec=google.auth.credentials.Credentials)
    client = Client(project=project, credentials=credentials)
    client._firestore_api_internal = firestore_api
    return client, client.document(doc_path)


def _run_testcase(testcase, call, firestore_api, client):
    if testcase.is_error:
        # TODO: is there a subclass of Exception we can check for?
        with pytest.raises(Exception):
            call()
    else:
        call()
        firestore_api.commit.assert_called_once_with(
            client._database_string,
            list(testcase.request.writes),
            transaction=None,
            metadata=client._rpc_metadata)


@pytest.mark.parametrize('test_proto', _CREATE_TESTPROTOS)
def test_create_testprotos(test_proto):
    testcase = test_proto.create
    firestore_api = _mock_firestore_api()
    client, document = _make_client_document(firestore_api, testcase)
    data = convert_data(json.loads(testcase.json_data))
    call = functools.partial(document.create, data)
    _run_testcase(testcase, call, firestore_api, client)


@pytest.mark.parametrize('test_proto', _GET_TESTPROTOS)
def test_get_testprotos(test_proto):
    testcase = test_proto.get
    try:
        testcase.is_error
    except AttributeError:
        return
    firestore_api = _mock_firestore_api()
    client, document = _make_client_document(firestore_api, testcase)
    call = functools.partial(document.get, None, None)
    _run_testcase(testcase, call, firestore_api, client)


@pytest.mark.parametrize('test_proto', _SET_TESTPROTOS)
def test_set_testprotos(test_proto):
    testcase = test_proto.set
    firestore_api = _mock_firestore_api()
    client, document = _make_client_document(firestore_api, testcase)
    data = convert_data(json.loads(testcase.json_data))
    if testcase.HasField("option"):
        merge = True
    else:
        merge = False
    call = functools.partial(document.set, data, merge)
    _run_testcase(testcase, call, firestore_api, client)


@pytest.mark.parametrize('test_proto', _UPDATE_TESTPROTOS)
def test_update_testprotos(test_proto):
    testcase = test_proto.update
    firestore_api = _mock_firestore_api()
    client, document = _make_client_document(firestore_api, testcase)
    data = convert_data(json.loads(testcase.json_data))
    if testcase.HasField("precondition"):
        option = convert_precondition(testcase.precondition)
    else:
        option = None
    call = functools.partial(document.update, data, option)
    _run_testcase(testcase, call, firestore_api, client)


@pytest.mark.skip(
    reason="Python has no way to call update with a list of field paths.")
@pytest.mark.parametrize('test_proto', _UPDATE_PATHS_TESTPROTOS)
def test_update_paths_testprotos(test_proto):
    pass


@pytest.mark.parametrize('test_proto', _DELETE_TESTPROTOS)
def test_delete_testprotos(test_proto):
    testcase = test_proto.delete
    firestore_api = _mock_firestore_api()
    client, document = _make_client_document(firestore_api, testcase)
    if testcase.HasField("precondition"):
        option = convert_precondition(testcase.precondition)
    else:
        option = None
    call = functools.partial(document.delete, option)
    _run_testcase(testcase, call, firestore_api, client)


@pytest.mark.skip(reason="Watch aka listen not yet implemented in Python.")
@pytest.mark.parametrize('test_proto', _LISTEN_TESTPROTOS)
def test_listen_paths_testprotos(test_proto):
    pass


def convert_data(v):
    # Replace the strings 'ServerTimestamp' and 'Delete' with the corresponding
    # sentinels.
    from google.cloud.firestore_v1beta1 import SERVER_TIMESTAMP, DELETE_FIELD

    if v == 'ServerTimestamp':
        return SERVER_TIMESTAMP
    elif v == 'Delete':
        return DELETE_FIELD
    elif isinstance(v, list):
        return [convert_data(e) for e in v]
    elif isinstance(v, dict):
        return {k: convert_data(v2) for k, v2 in v.items()}
    else:
        return v


def convert_precondition(precond):
    from google.cloud.firestore_v1beta1 import Client

    if precond.HasField('exists'):
        return Client.write_option(exists=precond.exists)
    else:  # update_time
        return Client.write_option(last_update_time=precond.update_time)
