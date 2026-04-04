from app.services import dita_graph_service


def test_parse_children_accepts_list_payloads():
    assert dita_graph_service._parse_children(["topicref", "keydef", ""]) == ["topicref", "keydef"]


def test_parse_attributes_accepts_dict_payloads():
    assert dita_graph_service._parse_attributes({"href": "optional", "format": "dita"}) == {
        "href": "optional",
        "format": "dita",
    }
