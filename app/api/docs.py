from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse


SWAGGER_TRANSLATION_SCRIPT = """
<script>
(() => {
  const translations = new Map([
    ["Authorize", "认证"],
    ["Available authorizations", "可用认证方式"],
    ["Cancel", "取消"],
    ["Clear", "清除"],
    ["Close", "关闭"],
    ["Code", "状态码"],
    ["Curl", "Curl 命令"],
    ["Default", "默认"],
    ["Description", "说明"],
    ["Download", "下载"],
    ["Example Value", "示例值"],
    ["Execute", "执行"],
    ["Links", "链接"],
    ["Media type", "媒体类型"],
    ["No links", "无链接"],
    ["No parameters", "无参数"],
    ["Parameters", "参数"],
    ["Request body", "请求体"],
    ["Request URL", "请求地址"],
    ["Required", "必填"],
    ["Reset", "重置"],
    ["Response body", "响应内容"],
    ["Response headers", "响应头"],
    ["Responses", "响应"],
    ["Schema", "数据结构"],
    ["Schemas", "数据模型"],
    ["Send empty value", "发送空值"],
    ["Server response", "服务器响应"],
    ["Servers", "服务器"],
    ["Successful Response", "请求成功"],
    ["Try it out", "在线调试"],
    ["Controls Accept header.", "控制 Accept 请求头。"]
  ]);

  function translate(root) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      const value = node.nodeValue.trim();
      if (!translations.has(value)) continue;
      const leading = node.nodeValue.match(/^\\s*/)[0];
      const trailing = node.nodeValue.match(/\\s*$/)[0];
      node.nodeValue = leading + translations.get(value) + trailing;
    }

    root.querySelectorAll?.("[placeholder], [title]").forEach((element) => {
      for (const attribute of ["placeholder", "title"]) {
        const value = element.getAttribute(attribute);
        if (translations.has(value)) {
          element.setAttribute(attribute, translations.get(value));
        }
      }
    });
  }

  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) {
        if (node.nodeType === Node.ELEMENT_NODE) translate(node);
      }
    }
  });

  translate(document.body);
  observer.observe(document.body, { childList: true, subtree: true });
})();
</script>
"""


def get_chinese_swagger_ui(*, openapi_url: str, title: str) -> HTMLResponse:
    page = get_swagger_ui_html(
        openapi_url=openapi_url,
        title=title,
        swagger_ui_parameters={
            "deepLinking": True,
            "displayRequestDuration": True,
            "docExpansion": "list",
            "filter": True,
        },
    )
    html = page.body.decode("utf-8").replace(
        "</body>",
        f"{SWAGGER_TRANSLATION_SCRIPT}</body>",
    )
    return HTMLResponse(content=html, status_code=page.status_code)
