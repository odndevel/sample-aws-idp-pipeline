from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.ddb import client, documents, projects, workflows


class TestDecimalToPython:
    def test_integer_decimal(self):
        result = client.decimal_to_python(Decimal("10"))
        assert result == 10
        assert isinstance(result, int)

    def test_float_decimal(self):
        result = client.decimal_to_python(Decimal("10.5"))
        assert result == 10.5
        assert isinstance(result, float)

    def test_dict_with_decimals(self):
        result = client.decimal_to_python({"count": Decimal("5"), "price": Decimal("9.99")})
        assert result == {"count": 5, "price": 9.99}

    def test_list_with_decimals(self):
        result = client.decimal_to_python([Decimal("1"), Decimal("2.5")])
        assert result == [1, 2.5]

    def test_nested_structure(self):
        result = client.decimal_to_python(
            {
                "items": [{"qty": Decimal("3")}],
                "total": Decimal("100"),
            }
        )
        assert result == {"items": [{"qty": 3}], "total": 100}

    def test_non_decimal_passthrough(self):
        assert client.decimal_to_python("hello") == "hello"
        assert client.decimal_to_python(42) == 42
        assert client.decimal_to_python(None) is None


class TestMakeKeys:
    def test_make_project_key(self):
        result = projects.make_project_key("proj-123")
        assert result == {"PK": "PROJ#proj-123", "SK": "META"}

    def test_make_document_key(self):
        result = documents.make_document_key("proj-123", "doc-456")
        assert result == {"PK": "PROJ#proj-123", "SK": "DOC#doc-456"}

    def test_make_workflow_link_key(self):
        result = workflows.make_workflow_link_key("proj-123", "wf-789")
        assert result == {"PK": "PROJ#proj-123", "SK": "WF#wf-789"}

    def test_make_workflow_meta_key(self):
        result = workflows.make_workflow_meta_key("wf-789")
        assert result == {"PK": "WF#wf-789", "SK": "META"}


class TestProjectHelpers:
    @pytest.fixture
    def mock_table(self):
        with patch("app.ddb.projects.get_table") as mock:
            table = MagicMock()
            mock.return_value = table
            yield table

    def test_get_project_item_found(self, mock_table):
        mock_table.get_item.return_value = {
            "Item": {
                "PK": "PROJ#test-id",
                "SK": "META",
                "data": {"project_id": "test-id", "name": "Test Project", "description": "", "status": "active"},
                "created_at": "2024-01-01T00:00:00+00:00",
                "updated_at": "2024-01-01T00:00:00+00:00",
                "GSI1PK": "PROJECTS",
                "GSI1SK": "2024-01-01T00:00:00+00:00",
            }
        }

        result = projects.get_project_item("test-id")

        assert result is not None
        assert result.data.name == "Test Project"
        mock_table.get_item.assert_called_once_with(Key={"PK": "PROJ#test-id", "SK": "META"})

    def test_get_project_item_not_found(self, mock_table):
        mock_table.get_item.return_value = {}

        result = projects.get_project_item("nonexistent")

        assert result is None

    @patch("app.ddb.projects.now_iso", return_value="2024-01-01T00:00:00+00:00")
    def test_put_project_item(self, mock_now, mock_table):
        data = {"project_id": "new-proj", "name": "New Project", "description": "", "status": "active"}

        projects.put_project_item("new-proj", data)

        mock_table.put_item.assert_called_once_with(
            Item={
                "PK": "PROJ#new-proj",
                "SK": "META",
                "data": data,
                "created_at": "2024-01-01T00:00:00+00:00",
                "updated_at": "2024-01-01T00:00:00+00:00",
                "GSI1PK": "PROJECTS",
                "GSI1SK": "2024-01-01T00:00:00+00:00",
            }
        )

    @patch("app.ddb.projects.now_iso", return_value="2024-01-01T00:00:00+00:00")
    def test_update_project_data(self, mock_now, mock_table):
        data = {"project_id": "test-id", "name": "Updated Name", "description": "", "status": "active"}

        projects.update_project_data("test-id", data)

        mock_table.update_item.assert_called_once_with(
            Key={"PK": "PROJ#test-id", "SK": "META"},
            UpdateExpression="SET #data = :data, updated_at = :updated_at, GSI1SK = :gsi1sk",
            ExpressionAttributeNames={"#data": "data"},
            ExpressionAttributeValues={":data": data, ":updated_at": "2024-01-01T00:00:00+00:00", ":gsi1sk": "2024-01-01T00:00:00+00:00"},
        )

    def test_query_all_project_items_single_page(self, mock_table):
        mock_table.query.return_value = {
            "Items": [
                {"PK": "PROJ#test-id", "SK": "PROJ#test-id"},
                {"PK": "PROJ#test-id", "SK": "DOC#doc-1"},
            ]
        }

        result = projects.query_all_project_items("test-id")

        assert len(result) == 2

    def test_query_all_project_items_with_pagination(self, mock_table):
        mock_table.query.side_effect = [
            {"Items": [{"PK": "PROJ#test-id", "SK": "DOC#1"}], "LastEvaluatedKey": {"PK": "PROJ#test-id"}},
            {"Items": [{"PK": "PROJ#test-id", "SK": "DOC#2"}]},
        ]

        result = projects.query_all_project_items("test-id")

        assert len(result) == 2
        assert mock_table.query.call_count == 2


class TestDocumentHelpers:
    @pytest.fixture
    def mock_table(self):
        with patch("app.ddb.documents.get_table") as mock:
            table = MagicMock()
            mock.return_value = table
            yield table

    def test_get_document_item_found(self, mock_table):
        mock_table.get_item.return_value = {
            "Item": {
                "PK": "PROJ#proj-1",
                "SK": "DOC#doc-1",
                "data": {
                    "document_id": "doc-1",
                    "project_id": "proj-1",
                    "name": "test.pdf",
                    "file_type": "application/pdf",
                    "file_size": 1024,
                    "status": "completed",
                    "s3_key": "projects/proj-1/documents/doc-1/test.pdf",
                },
                "GSI1PK": "PROJ#proj-1#DOC",
                "GSI1SK": "2024-01-01T00:00:00+00:00",
                "created_at": "2024-01-01T00:00:00+00:00",
                "updated_at": "2024-01-01T00:00:00+00:00",
            }
        }

        result = documents.get_document_item("proj-1", "doc-1")

        assert result is not None
        assert result.data.name == "test.pdf"

    def test_get_document_item_not_found(self, mock_table):
        mock_table.get_item.return_value = {}

        result = documents.get_document_item("proj-1", "nonexistent")

        assert result is None

    @patch("app.ddb.documents.now_iso", return_value="2024-01-01T00:00:00+00:00")
    def test_put_document_item(self, mock_now, mock_table):
        data = {
            "document_id": "doc-1",
            "project_id": "proj-1",
            "name": "test.pdf",
            "file_type": "application/pdf",
            "file_size": 1024,
            "status": "uploaded",
            "s3_key": "projects/proj-1/documents/doc-1/test.pdf",
        }

        documents.put_document_item("proj-1", "doc-1", data)

        mock_table.put_item.assert_called_once_with(
            Item={
                "PK": "PROJ#proj-1",
                "SK": "DOC#doc-1",
                "GSI1PK": "PROJ#proj-1#DOC",
                "GSI1SK": "2024-01-01T00:00:00+00:00",
                "data": data,
                "created_at": "2024-01-01T00:00:00+00:00",
                "updated_at": "2024-01-01T00:00:00+00:00",
            }
        )

    def test_query_documents(self, mock_table):
        mock_table.query.return_value = {
            "Items": [
                {
                    "PK": "PROJ#proj-1",
                    "SK": "DOC#doc-1",
                    "GSI1PK": "PROJ#proj-1#DOC",
                    "GSI1SK": "2024-01-01T00:00:00+00:00",
                    "data": {
                        "document_id": "doc-1",
                        "project_id": "proj-1",
                        "name": "a.pdf",
                        "file_type": "application/pdf",
                        "file_size": 1024,
                        "status": "completed",
                        "s3_key": "test",
                    },
                    "created_at": "2024-01-01T00:00:00+00:00",
                    "updated_at": "2024-01-01T00:00:00+00:00",
                },
                {
                    "PK": "PROJ#proj-1",
                    "SK": "DOC#doc-2",
                    "GSI1PK": "PROJ#proj-1#DOC",
                    "GSI1SK": "2024-01-01T00:00:00+00:00",
                    "data": {
                        "document_id": "doc-2",
                        "project_id": "proj-1",
                        "name": "b.pdf",
                        "file_type": "application/pdf",
                        "file_size": 2048,
                        "status": "completed",
                        "s3_key": "test2",
                    },
                    "created_at": "2024-01-01T00:00:00+00:00",
                    "updated_at": "2024-01-01T00:00:00+00:00",
                },
            ]
        }

        result = documents.query_documents("proj-1")

        assert len(result) == 2

    def test_delete_document_item(self, mock_table):
        documents.delete_document_item("proj-1", "doc-1")

        mock_table.delete_item.assert_called_once_with(Key={"PK": "PROJ#proj-1", "SK": "DOC#doc-1"})


class TestWorkflowHelpers:
    @pytest.fixture
    def mock_table(self):
        with patch("app.ddb.workflows.get_table") as mock:
            table = MagicMock()
            mock.return_value = table
            yield table

    def test_get_workflow_meta_found(self, mock_table):
        mock_table.get_item.return_value = {
            "Item": {
                "PK": "WF#wf-1",
                "SK": "META",
                "data": {"status": "completed", "total_segments": Decimal("5")},
            }
        }

        result = workflows.get_workflow_meta("wf-1")

        assert result is not None
        assert result["data"]["total_segments"] == 5  # Decimal converted

    def test_get_workflow_meta_not_found(self, mock_table):
        mock_table.get_item.return_value = {}

        result = workflows.get_workflow_meta("nonexistent")

        assert result is None

    def test_query_workflows(self, mock_table):
        mock_table.query.return_value = {
            "Items": [
                {"PK": "PROJ#proj-1", "SK": "WF#wf-1", "data": {"status": "completed"}},
                {"PK": "PROJ#proj-1", "SK": "WF#wf-2", "data": {"status": "pending"}},
            ]
        }

        result = workflows.query_workflows("proj-1")

        assert len(result) == 2

    def test_query_workflow_segments(self, mock_table):
        mock_table.query.return_value = {
            "Items": [
                {"PK": "WF#wf-1", "SK": "SEG#0", "data": {"segment_index": Decimal("0")}},
                {"PK": "WF#wf-1", "SK": "SEG#1", "data": {"segment_index": Decimal("1")}},
            ]
        }

        result = workflows.query_workflow_segments("wf-1")

        assert len(result) == 2
        assert result[0]["data"]["segment_index"] == 0  # Decimal converted

    def test_delete_workflow_link(self, mock_table):
        workflows.delete_workflow_link("proj-1", "wf-1")

        mock_table.delete_item.assert_called_once_with(Key={"PK": "PROJ#proj-1", "SK": "WF#wf-1"})


class TestBatchDelete:
    @pytest.fixture
    def mock_table(self):
        with patch("app.ddb.client.get_table") as mock:
            table = MagicMock()
            mock.return_value = table
            yield table

    def test_batch_delete_items(self, mock_table):
        mock_batch_writer = MagicMock()
        mock_table.batch_writer.return_value.__enter__ = MagicMock(return_value=mock_batch_writer)
        mock_table.batch_writer.return_value.__exit__ = MagicMock(return_value=False)

        items = [
            {"PK": "PROJ#p1", "SK": "DOC#d1"},
            {"PK": "PROJ#p1", "SK": "DOC#d2"},
        ]

        client.batch_delete_items(items)

        assert mock_batch_writer.delete_item.call_count == 2
