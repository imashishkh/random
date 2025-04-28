// scripts/health-dashboard.js
const express = require('express');
const Docker = require('dockerode');
const app = express();
const docker = new Docker();

function generateDashboardHtml(healthData) {
  const healthRows = healthData.map(container => {
    const healthClass = container.health === 'healthy' ? 'text-success' : 
                        container.health === 'unhealthy' ? 'text-danger' : 'text-warning';
    return `
      <tr>
        <td>${container.name}</td>
        <td class="${healthClass}">${container.health}</td>
        <td>${new Date(container.startedAt).toLocaleString()}</td>
        <td>${container.restartCount}</td>
      </tr>
    `;
  }).join('');

  return `
    <!DOCTYPE html>
    <html>
    <head>
      <title>FX-Swarm Health Dashboard</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body>
      <div class="container mt-4">
        <h1>FX-Swarm Health Dashboard</h1>
        <p class="text-muted">Last updated: ${new Date().toLocaleString()}</p>
        <table class="table table-striped">
          <thead>
            <tr>
              <th>Service</th>
              <th>Health</th>
              <th>Started At</th>
              <th>Restart Count</th>
            </tr>
          </thead>
          <tbody>
            ${healthRows}
          </tbody>
        </table>
      </div>
      <script>
        setTimeout(() => location.reload(), 10000);  // Refresh every 10 seconds
      </script>
    </body>
    </html>
  `;
}

app.get('/', async (req, res) => {
  try {
    const containers = await docker.listContainers({all: true});
    const healthData = await Promise.all(containers.map(async container => {
      const containerInfo = await docker.getContainer(container.Id).inspect();
      return {
        name: containerInfo.Name.replace('/', ''),
        health: containerInfo.State.Health?.Status || 'no health check',
        startedAt: containerInfo.State.StartedAt,
        restartCount: containerInfo.RestartCount
      };
    }));
    
    res.send(generateDashboardHtml(healthData));
  } catch (error) {
    res.status(500).send(`Error: ${error.message}`);
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Health dashboard running on port ${PORT}`);
}); 