// helpers/formatResponse.js

/**
 * Standardizes API responses.
 * @param {object} reply - Fastify reply object.
 * @param {object} options - Response options.
 * @param {number} [options.statusCode=200] - HTTP status code.
 * @param {*} [options.data=null] - The main data payload.
 * @param {object|null} [options.meta=null] - Metadata (pagination, messages, etc.).
 * @param {object|null} [options.links=null] - Navigation links.
 * @param {object|null} [options.error=null] - Error details { code, message, details }.
 */
export function formatResponse(reply, { statusCode = 200, data = null, meta = null, links = null, error = null }) {
  const body = {};

  if (error) {
    // Ensure error has a standard structure
    body.error = {
      code: error.code || 'INTERNAL_SERVER_ERROR', // Default error code
      message: error.message || 'An unexpected error occurred.',
      details: error.details || null,
    };
    // Ensure other top-level keys exist but are null for errors
    body.data = null;
    body.meta = null;
    body.links = null;
  } else {
    body.data = data;
    body.meta = meta;
    body.links = links;
    // Ensure error key exists but is null for success
    body.error = null;
  }

  return reply.code(statusCode).send(body);
}

/**
 * Builds standard pagination links.
 * @param {object} request - Fastify request object.
 * @param {object} meta - The calculated pagination metadata.
 * @returns {object} - Links object { first, prev, next, last }.
 */
export function buildPaginationLinks(request, meta) {
  if (!meta || meta.last_page <= 1) { // No pagination needed if only one page
    return { first: null, prev: null, next: null, last: null };
  }

  const baseUrl = `${request.protocol}://${request.headers.host}${request.raw.url.split('?')[0]}`;
  const queryParams = new URLSearchParams(request.query);
  const limit = meta.per_page; // Use per_page from meta as the limit

  const buildLink = (newOffset) => {
    queryParams.set('offset', newOffset);
    queryParams.set('limit', limit);
    return `${baseUrl}?${queryParams.toString()}`;
  };

  return {
    first: buildLink(0),
    prev: meta.has_prev ? buildLink(Math.max(meta.offset - limit, 0)) : null,
    next: meta.has_next ? buildLink(meta.offset + limit) : null,
    last: buildLink((meta.last_page - 1) * limit),
  };
}