// src/config/env.js

import dotenv from 'dotenv';

// Load .env file ke process.env
dotenv.config();

const { HOST = '0.0.0.0', PORT = 4000, SECRET = '210491',ZENIX_API_AUTH_USER,ZENIX_API_AUTH_PASS } = process.env;

if (isNaN(PORT)) {
  console.error('Error: Invalid PORT environment variable. Must be a number.');
  process.exit(1);
}

export { HOST, PORT, SECRET,ZENIX_API_AUTH_USER,ZENIX_API_AUTH_PASS };
