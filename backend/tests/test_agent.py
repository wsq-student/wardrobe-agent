import json
from langchain_core.messages import AIMessage
from app import agent


class ModelStub:
    def __init__(self, candidates):
        self.candidates = iter(candidates)
        self.tool_mode = False
        self.round = 0

    def bind_tools(self, tools):
        self.tool_mode = True
        return self

    def bind(self, **kwargs):
        self.tool_mode = False
        return self

    def invoke(self, messages):
        if self.tool_mode:
            self.round += 1
            if self.round == 1:
                return AIMessage(content='', tool_calls=[{'name':'search_wardrobe','args':{},'id':'call1','type':'tool_call'}])
            return AIMessage(content='已查询')
        return AIMessage(content=json.dumps({'item_ids':next(self.candidates),'reason':'通勤搭配','clarification':'','warnings':[]}))


def test_graph_repairs_hallucinated_ids_and_calls_tools(monkeypatch):
    monkeypatch.setattr(agent, 'model', lambda: ModelStub([[1, 999], [1, 2]]))
    trace = []
    items = [dict(id=1, category='tops',status='available'),dict(id=2, category='bottoms',status='available')]
    result = agent.recommend('通勤', [], items, {}, [], trace.append)
    assert result['item_ids'] == [1, 2]
    assert any(t['stage'] == 'tool' for t in trace)
    assert any(t['stage'] == 'repair' for t in trace)


def test_graph_fails_closed_after_invalid_repair(monkeypatch):
    monkeypatch.setattr(agent, 'model', lambda: ModelStub([[99], [99]]))
    result = agent.recommend('推荐', [], [], {}, [], lambda event: None)
    assert result['item_ids'] == []
    assert result['clarification']
