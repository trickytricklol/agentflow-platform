import json
from unittest.mock import patch

from agentflow.providers import ChatMessage, MockProvider, OllamaProvider


def test_mock_provider_contract():
    result = MockProvider("ok").chat([ChatMessage("user", "hello")], model="demo")
    assert result.content == "ok"
    assert result.model == "demo"


def test_native_ollama_provider_maps_generation_options_and_strips_openai_tool_choice():
    class Response:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self):
            return json.dumps({'model':'local','message':{'content':'ok'},'prompt_eval_count':3,'eval_count':2}).encode()
    captured={}
    def fake_open(request,timeout):
        captured['payload']=json.loads(request.data.decode()); captured['timeout']=timeout; return Response()
    provider=OllamaProvider(timeout=9)
    with patch('agentflow.providers.base.urlopen',fake_open):
        result=provider.chat([ChatMessage('user','hi')],model='local',seed=7,max_tokens=128,think=False,tool_choice='required')
    assert result.content=='ok' and result.input_tokens==3 and result.output_tokens==2
    assert captured['payload']['options']=={'temperature':0.0,'seed':7,'num_predict':128}
    assert captured['payload']['think'] is False and 'tool_choice' not in captured['payload']
