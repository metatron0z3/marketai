export default () => ({
  port: parseInt(process.env.PORT, 10) || 3000,
  questdb: {
    host: process.env.QUESTDB_HOST || 'questdb',
    port: parseInt(process.env.QUESTDB_PORT, 10) || 8812,
    user: process.env.QUESTDB_USER || 'admin',
    password: process.env.QUESTDB_PASSWORD || 'quest',
    database: process.env.QUESTDB_DATABASE || 'qdb',
  },
  pythonService: {
    url: process.env.PYTHON_SERVICE_URL || 'http://python-service:8000',
  },
});
