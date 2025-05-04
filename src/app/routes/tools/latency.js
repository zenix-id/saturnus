import fp from 'fastify-plugin';
import axios from 'axios';
import ping from 'ping';
import { URL } from 'url';

/**
 * Checks if a string is a valid URL with an http or https scheme.
 * @param {string} string - The string to check.
 * @returns {boolean} - True if it's a valid URL with http/https, false otherwise.
 */
function isUrlWithHttpScheme(string) {
  try {
    const parsedUrl = new URL(string);
    return ['http:', 'https:'].includes(parsedUrl.protocol);
  } catch (_) {
    return false; // Parsing failed, not a valid URL
  }
}

/**
 * Measures latency using an HTTP GET request.
 * @param {string} url - The target URL.
 * @returns {Promise<{success: boolean, latency?: number, error?: string}>} - The measurement result.
 */
async function checkHttpLatency(url) {
  const start = process.hrtime();
  try {
    // 5-second timeout for HTTP request
    await axios.get(url, { timeout: 5000 });
    const diff = process.hrtime(start);
    const latencyMs = (diff[0] * 1e9 + diff[1]) / 1e6;
    // Return latency as a number (float)
    return { success: true, latency: latencyMs };
  } catch (err) {
    const diffFail = process.hrtime(start);
    // Report time until failure
    const latencyToFailMs = (diffFail[0] * 1e9 + diffFail[1]) / 1e6;
    return { success: false, error: err.message, latency: latencyToFailMs };
  }
}

/**
 * Measures latency using ICMP Echo (ping).
 * @param {string} host - The target hostname or IP address.
 * @returns {Promise<{success: boolean, latency?: number, error?: string}>} - The measurement result.
 */
async function checkIcmpLatency(host) {
  try {
    // 5-second timeout for ping
    const res = await ping.promise.probe(host, { timeout: 5 });
    if (res.alive && typeof res.time === 'number') {
      // Use the time reported by the ping library (already in ms, possibly float)
      return { success: true, latency: res.time };
    } else {
      // Host didn't respond or time is unknown
      return { success: false, error: `Host did not respond or ping time unknown. Alive: ${res.alive}, Time: ${res.time}` };
    }
  } catch (err) {
     // Error trying to ping (e.g., DNS resolution failure)
     return { success: false, error: `Ping probe failed: ${err.message || 'Unknown error'}` };
  }
}

/**
 * Fastify plugin for the latency measurement endpoint.
 */
async function latencyCheckRoute(fastify, opts) {
  fastify.get('/api/latency', async (request, reply) => {
    const { host } = request.query;

    if (!host) {
      return reply.status(400).send({
        statusCode: 400,
        message: 'Parameter "host" is required. Example: /api/latency?host=https://google.com or /api/latency?host=8.8.8.8'
      });
    }

    let result;
    let checkType = 'ICMP (ping)'; // Default to ping

    // Detect: If it looks like a URL with http/https scheme, use HTTP
    if (isUrlWithHttpScheme(host)) {
       checkType = 'HTTP (axios)';
       fastify.log.info(`Measuring ${checkType} latency for: ${host}`);
       result = await checkHttpLatency(host);
    } else {
       // Otherwise, try ping (for IP or hostname)
       fastify.log.info(`Measuring ${checkType} latency for: ${host}`);
       result = await checkIcmpLatency(host);
    }

    // Send response based on the result
    if (result.success && result.latency !== undefined) {
      // *** MODIFICATION: Return latency as an integer ***
      return reply.send({
        statusCode: 200,
        message: `Latency (${checkType}) to ${host} measured successfully.`,
        // Round the latency to the nearest whole number
        latency: Math.round(result.latency)
      });
    } else {
       // Use 502 Bad Gateway if the target is unreachable or failed
       const responsePayload = {
         statusCode: 502,
         message: `Failed to contact host (${checkType}): ${host}`,
         error: result.error || 'Unknown error during check', // Ensure error is always present
       };
       // Include latency (time until failure) if available, keeping it descriptive
       if (result.latency !== undefined) {
           // Keep latency_detail as a descriptive string for failures
           responsePayload.latency_detail = `Time until failure: ${result.latency.toFixed(2)} ms`;
       }
      return reply.status(502).send(responsePayload);
    }
  });
}

// Export the plugin
export default fp(latencyCheckRoute, {
  name: 'latency-checker',
  dependencies: []
});

