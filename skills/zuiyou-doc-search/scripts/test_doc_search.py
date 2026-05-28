# test_doc_search.py
from doc_search_runner import html_to_markdown, parse_args, load_env_token

def test_html_to_markdown():
    sample_html = """
    <p><br/></p><h2 id="id-最右线上推荐服务mongo/redis梳理-在线服务使用mongo、redis业务逻辑梳理">在线服务使用mongo、redis 业务逻辑梳理</h2><p><br/></p>
    <div class="table-wrap">
    <table class="wrapped confluenceTable">
    <tbody>
    <tr><th>使用接口/代码</th><th>Mongo/Redis</th><th>功能</th></tr>
    <tr><td>vendor/git.ixiaochuan.cn</td><td>item_show_redis</td><td>更新新帖曝光，用于保量</td></tr>
    </tbody>
    </table>
    </div>
    """
    markdown = html_to_markdown(sample_html)
    print("--- Tested Markdown Output ---")
    print(markdown)
    assert "在线服务使用mongo、redis 业务逻辑梳理" in markdown
    assert "vendor/git.ixiaochuan.cn" in markdown
    assert "item_show_redis" in markdown
    print("Test passed successfully!")

def test_parse_keyword_with_spaces_does_not_treat_second_word_as_limit():
    token, keyword, limit = parse_args(["怦怦", "怦自研模型", "qwen2572_peng_3"], env_token="env-token")
    assert token == "env-token"
    assert keyword == "怦怦 怦自研模型 qwen2572_peng_3"
    assert limit == 15

def test_parse_keyword_with_trailing_limit():
    token, keyword, limit = parse_args(["怦怦", "怦自研模型", "qwen2572_peng_3", "5"], env_token="env-token")
    assert token == "env-token"
    assert keyword == "怦怦 怦自研模型 qwen2572_peng_3"
    assert limit == 5

def test_parse_explicit_limit_flag():
    token, keyword, limit = parse_args(["--limit", "7", "hello", "world"], env_token="env-token")
    assert token == "env-token"
    assert keyword == "hello world"
    assert limit == 7

def test_load_env_token_reads_quoted_value():
    token = load_env_token()
    assert token
    assert "=" not in token

if __name__ == "__main__":
    test_html_to_markdown()
    test_parse_keyword_with_spaces_does_not_treat_second_word_as_limit()
    test_parse_keyword_with_trailing_limit()
    test_parse_explicit_limit_flag()
    test_load_env_token_reads_quoted_value()
