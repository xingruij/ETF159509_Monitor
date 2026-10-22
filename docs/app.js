(() => {
  const form = document.getElementById('settings-form');
  const status = document.getElementById('status');
  const saveButton = document.getElementById('save');
  const setStatus = (message, ok = false) => {
    status.textContent = message;
    status.style.color = ok ? '#15803d' : '#b42318';
  };

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const owner = document.getElementById('owner').value.trim();
    const repo = document.getElementById('repo').value.trim();
    const branch = document.getElementById('branch').value.trim() || 'main';
    const token = document.getElementById('token').value.trim();
    const threshold = Number(document.getElementById('threshold').value);
    if (!owner || !repo || !branch || !token || !Number.isFinite(threshold) || threshold < -100 || threshold > 1000) {
      setStatus('请检查必填项；阈值需在 -100 到 1000 之间。'); return;
    }
    saveButton.disabled = true;
    setStatus('正在读取当前配置…', true);
    const api = `https://api.github.com/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/contents/config.json`;
    const headers = {
      'Accept': 'application/vnd.github+json',
      'Authorization': `Bearer ${token}`,
      'X-GitHub-Api-Version': '2022-11-28'
    };
    try {
      const getResponse = await fetch(`${api}?ref=${encodeURIComponent(branch)}`, { headers, cache: 'no-store' });
      if (!getResponse.ok) throw new Error(`读取失败（HTTP ${getResponse.status}）。请检查仓库名、分支和 Token 权限。`);
      const file = await getResponse.json();
      const current = JSON.parse(decodeURIComponent(escape(atob(file.content.replace(/\n/g, '')))));
      current.threshold_pct = Math.round(threshold * 100) / 100;
      const content = btoa(unescape(encodeURIComponent(JSON.stringify(current, null, 2) + '\n')));
      setStatus('正在写入 config.json…', true);
      const putResponse = await fetch(api, {
        method: 'PUT',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: `Update ETF premium threshold to ${current.threshold_pct.toFixed(2)}%`,
          content,
          sha: file.sha,
          branch
        })
      });
      if (!putResponse.ok) {
        const detail = await putResponse.json().catch(() => ({}));
        throw new Error(`写入失败（HTTP ${putResponse.status}）：${detail.message || '请检查 Contents: Read and write 权限。'}`);
      }
      document.getElementById('token').value = '';
      setStatus(`保存成功：阈值已设置为 ${current.threshold_pct.toFixed(2)}%。建议现在手动运行一次 GitHub Actions 检查。Token 已从表单清空。`, true);
    } catch (error) {
      setStatus(error.message || '操作失败，请稍后重试。');
    } finally {
      saveButton.disabled = false;
    }
  });
})();
