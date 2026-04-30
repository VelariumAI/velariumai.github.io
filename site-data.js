(async function () {
  function setTextByProject(projectKey, value) {
    if (!value) return;
    var nodes = document.querySelectorAll('[data-project-desc="' + projectKey + '"]');
    nodes.forEach(function (node) {
      node.textContent = value;
    });
  }

  function setMetaByProject(projectKey, data) {
    var nodes = document.querySelectorAll('[data-project-meta="' + projectKey + '"]');
    nodes.forEach(function (node) {
      var parts = [];
      if (data.latest_release) parts.push("Latest: " + data.latest_release);
      if (data.updated_at) parts.push("Updated: " + data.updated_at.slice(0, 10));
      node.textContent = parts.join(" · ");
      node.hidden = parts.length === 0;
    });
  }

  try {
    var res = await fetch("projects.json", { cache: "no-store" });
    if (!res.ok) return;
    var payload = await res.json();
    var projects = payload && payload.projects ? payload.projects : {};
    Object.keys(projects).forEach(function (key) {
      var project = projects[key];
      setTextByProject(key, project.description);
      setMetaByProject(key, project);
    });
  } catch (err) {
    /* Keep static fallback copy if fetch fails. */
  }
})();
