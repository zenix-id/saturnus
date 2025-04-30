// config/logger.js
// Logger configuration with Pino Pretty
const loggerConfig = {
  transport: {
    target: 'pino-pretty',
    options: {
      translateTime: 'SYS:HH:MM:ss Z',
      ignore: 'pid,hostname',
    },
  },
};

const logger = loggerConfig

export default logger;
