import fp from 'fastify-plugin';
import { formatResponse, buildPaginationLinks } from '../helpers/formatResponse.js'; // <-- Sesuaikan path
import { ZENIX_API_AUTH_USER,ZENIX_API_AUTH_PASS } from '../../config/server.js';
const BASE_MINIMAL_FIELDS = ['id', 'display_name', 'write_date'];
const OPTIONAL_MINIMAL_FIELDS = ['stage_id', 'partner_id', 'state', 'user_id', 'status','company_id', 'tag_ids','team_ids','product_id','reference'];
const POTENTIAL_MINIMAL_FIELDS = [...BASE_MINIMAL_FIELDS, ...OPTIONAL_MINIMAL_FIELDS];

// Helper untuk mendapatkan field yang valid untuk suatu model (dengan caching & logging)
async function getValidFieldsForModel(con, model, request) {
  if (!request.validFieldsCache) {
    request.validFieldsCache = {};
  }
  if (request.validFieldsCache[model]) {
    request.log.info({ reqId: request.id, model }, `[Cache Hit] Using cached valid fields for model.`);
    return request.validFieldsCache[model];
  }

  request.log.info({ reqId: request.id, model }, `Attempting con.getFields for model`);
  try {
    // Menggunakan con.getFields(model)
    const fieldsInfo = await con.getFields(model); // Anda konfirmasi ini metode yang benar
    if (!fieldsInfo || typeof fieldsInfo !== 'object') {
        request.log.error({ reqId: request.id, model, returnType: typeof fieldsInfo }, `con.getFields did not return a valid object.`);
        throw new Error(`getFields for model ${model} did not return a valid object.`);
    }

    const validFieldNames = Object.keys(fieldsInfo);
    request.log.info({ reqId: request.id, model, count: validFieldNames.length }, `[Cache Miss] Successfully retrieved valid fields. Example: [${validFieldNames.slice(0, 15).join(', ')}${validFieldNames.length > 15 ? ', ...' : ''}]`);
    request.validFieldsCache[model] = validFieldNames; // Cache hasil
    return validFieldNames;
  } catch (err) {
    request.log.error({ reqId: request.id, model, err }, `Failed during con.getFields execution`);
    return []; // Return empty array on error to avoid breaking flow
  }
}


async function beApiRoutes(fastify, opts) {

  // --- Authentication Routes (Tetap Sama) ---
  fastify.post('/api/auth', async (request, reply) => {
    const { username, password } = request.body || {};
    if (!username || !password) return formatResponse(reply, { statusCode: 400, error: { code: 'MISSING_CREDENTIALS' }});
    try {
        const con = await fastify.auth(username, password);
        if (!con) return formatResponse(reply, { statusCode: 401, error: { code: 'AUTH_FAILED' }});
        const token = fastify.jwt.sign({ username,password }, { expiresIn: '1h' });
        const refreshToken = await reply.jwtSign({ username,password }, { expiresIn: '7d' });
        reply.setCookie('refreshToken', refreshToken, { path: '/', secure: process.env.NODE_ENV === 'production', httpOnly: true, sameSite: 'lax' });
        return formatResponse(reply, { statusCode: 200, data: { token } });
    } catch (err) {
        request.log.error(err, 'Auth error');
        return formatResponse(reply, { statusCode: 500, error: { code: 'AUTH_ERROR' } });
    }
  });
  fastify.post('/api/auth/refresh', async (request, reply) => {
      try {
          const decoded = await request.jwtVerify({ onlyCookie: true });
          const token = fastify.jwt.sign({ username: decoded.username }, { expiresIn: '1h' });
          return formatResponse(reply, { statusCode: 200, data: { token } });
      } catch (err) {
          request.log.warn(err, 'Refresh token failed');
          reply.clearCookie('refreshToken');
          return formatResponse(reply, { statusCode: 401, error: { code: 'INVALID_REFRESH_TOKEN' } });
      }
  });

  // --- Hook JWT (Tetap Sama) ---
  fastify.addHook('onRequest', async (request, reply) => {
    if (request.url.startsWith('/api/auth')) return;
    if (request.url.startsWith('/api/be')) {
        try {
            request.user = await request.jwtVerify();
        } catch (err) {
            request.log.warn({ url: request.url, error: err.message }, 'JWT verification failed');
            formatResponse(reply, { statusCode: 401, error: { code: 'UNAUTHENTICATED' } });
            throw new Error('Authentication Required');
        }
    }
  });


  // --- GET /api/be (List resources or models) ---
  fastify.get('/api/be', async (request, reply) => {
    const reqId = request.id; // Ambil request ID untuk logging
    request.log.info({ reqId, query: request.query }, 'Handling GET /api/be request');

    try {
      const { username, password } = request.user;
      request.log.info({ username, password }, 'Handling GET /api/be request');
      const con = await fastify.auth(username, password);
      if (!con) throw new Error('Odoo connection failed.');

      const model = request.query.model;
      const reqOffset = request.query.offset;
      const reqLimit = request.query.limit;
      const explicitlyRequestedFields = request.query.fields ? request.query.fields.split(',').map(f => f.trim()).filter(f => f) : undefined;
      const detailMode = request.query.detail === 'true';
      const domain = []; // TODO: Parse domain

      const offset = Math.max(0, parseInt(reqOffset ?? 0));
      const reqLimitParsed = parseInt(reqLimit ?? 0);
      const isPaginationRequested = reqOffset !== undefined && reqLimit !== undefined && reqLimitParsed > 0;
      const limit = isPaginationRequested ? reqLimitParsed : 0;

      let responseData = [];
      let totalRecords = 0;
      let meta;
      let links;
      let fieldsToRequest; // Field yang akan diminta

      const commonOptions = { context: { lang: "en_US" } };

      if (!model) {
        // --- Kasus 1: List available models ---
        request.log.info({ reqId }, 'Listing available models (ir.model)');
        responseData = await con.searchRead('ir.model', {}, ["name", "model"], commonOptions);
        totalRecords = responseData.length;
        meta = { total: totalRecords, per_page: totalRecords, current_page: 1, last_page: 1, offset: 0, limit: totalRecords, from: totalRecords > 0 ? 1 : 0, to: totalRecords, has_next: false, has_prev: false };
        links = buildPaginationLinks(request, meta);

      } else {
        // --- Kasus 2: List records for a specific model ---
        request.log.info({ reqId, model, detailMode, explicitlyRequestedFields }, 'Listing records for specific model');

        // Tentukan fields yang akan diminta
        if (detailMode) {
            fieldsToRequest = explicitlyRequestedFields;
            request.log.info({ reqId, model }, `Detail mode TRUE. Requesting fields: ${fieldsToRequest ? `[${fieldsToRequest.join(', ')}]` : 'ALL (Default)'}`);
        } else {
            const validFieldNames = await getValidFieldsForModel(con, model, request);
            if (validFieldNames.length === 0) {
                 request.log.warn({ reqId, model }, 'Could not get valid fields from getFields, defaulting to id, display_name');
                 fieldsToRequest = ['id', 'display_name'];
            } else {
                // Filter field potensial HANYA dengan yang valid
                const actualMinimalFields = POTENTIAL_MINIMAL_FIELDS.filter(field => validFieldNames.includes(field));
                request.log.info({ reqId, model, potential: POTENTIAL_MINIMAL_FIELDS.join(','), valid_count: validFieldNames.length, filtered: actualMinimalFields.join(',') }, 'Filtering minimal fields against valid ones');

                // Pastikan field dasar yang valid selalu ada
                const baseValid = BASE_MINIMAL_FIELDS.filter(f => validFieldNames.includes(f));
                fieldsToRequest = [...new Set([...baseValid, ...actualMinimalFields])]; // Gabung dan unikkan

                if (fieldsToRequest.length === 0) {
                    // Fallback jika bahkan base field tidak ada (sangat aneh)
                    fieldsToRequest = validFieldNames.includes('id') ? ['id'] : []; // Minimal ID jika ada
                    request.log.warn({ reqId, model, final_fallback: fieldsToRequest.join(',') }, 'No minimal fields were valid, falling back');
                }
            }
            request.log.info({ reqId, model }, `Detail mode FALSE. Final fields to request: [${fieldsToRequest.join(', ')}]`);
        }

        // Dapatkan semua ID yang cocok
        const allIds = await con.search(model, domain, commonOptions);
        totalRecords = allIds.length;
        request.log.info({ reqId, model, totalRecords }, `Found total matching record IDs`);

        if (totalRecords > 0) {
            let idsToRead = allIds;
            if (isPaginationRequested) {
                idsToRead = allIds.slice(offset, offset + limit);
                request.log.info({ reqId, model, offset, limit, count: idsToRead.length }, 'Pagination applied to IDs');
            }

            if (idsToRead.length > 0) {
                request.log.info({ reqId, model, count: idsToRead.length, fields: fieldsToRequest || 'DEFAULT' }, 'Reading records...');
                // Gunakan con.read dengan ID yang sudah di-slice/semua dan fields yang sudah ditentukan
                responseData = await con.read(model, idsToRead, fieldsToRequest, commonOptions);
                request.log.info({ reqId, model, readCount: responseData.length }, 'Read successful');
            } else {
                 request.log.info({ reqId, model }, 'No IDs to read for this page/offset');
            }
        }

        // Kalkulasi Metadata
        const metaPerPage = isPaginationRequested ? limit : (totalRecords > 0 ? totalRecords : 0);
        const metaLimit = isPaginationRequested ? limit : (totalRecords > 0 ? totalRecords : 0);
        const calculatedLastPage = (isPaginationRequested && limit > 0) ? Math.ceil(totalRecords / limit) : 1;
        meta = { total: totalRecords, per_page: metaPerPage, current_page: (isPaginationRequested && limit > 0) ? (Math.floor(offset / limit) + 1) : 1, last_page: calculatedLastPage > 0 ? calculatedLastPage : 1, offset: offset, limit: metaLimit, from: totalRecords > 0 ? offset + 1 : 0, to: offset + responseData.length, has_next: isPaginationRequested && (offset + limit < totalRecords), has_prev: isPaginationRequested && offset > 0 };
        links = buildPaginationLinks(request, meta);
      }

      // --- Kirim respons sukses ---
      request.log.info({ reqId }, 'Sending successful response');
      return formatResponse(reply, { statusCode: 200, data: responseData, meta, links });

    } catch (error) {
      request.log.error({ reqId, err: error }, `Error in GET /api/be for model "${request.query.model || 'ir.model'}"`);
      // Penanganan error
      if (error.message?.includes('AccessError')) return formatResponse(reply, { statusCode: 403, error: { code: 'FORBIDDEN' } });
      if (error.message?.includes('Model not found')) return formatResponse(reply, { statusCode: 404, error: { code: 'NOT_FOUND', message: `Model '${request.query.model}' not found.` } });
      if (error.message?.includes('Invalid field')) return formatResponse(reply, { statusCode: 400, error: { code: 'INVALID_FIELD', message: error.message } });
      return formatResponse(reply, { statusCode: 500, error: { code: 'FETCH_FAILED', message: error.message || 'Failed to retrieve data.' } });
    }
  });

  // --- GET /api/be/:id (Get specific resource by ID) ---
  fastify.get('/api/be/:id', async (request, reply) => {
    const reqId = request.id;
    request.log.info({ reqId, params: request.params, query: request.query }, 'Handling GET /api/be/:id request');

    try {
        const { username, password } = request.user;
        
        // const con = await fastify.auth(username, password);
        const con = await fastify.auth(ZENIX_API_AUTH_USER,ZENIX_API_AUTH_PASS);
        if (!con) throw new Error('Odoo connection failed.');

        const { id } = request.params;
        const { model } = request.query;
        const explicitlyRequestedFields = request.query.fields ? request.query.fields.split(',').map(f => f.trim()).filter(f => f) : undefined;
        const detailMode = request.query.detail === 'true';

        // Validasi
        if (!model) return formatResponse(reply, { statusCode: 400, error: { code: 'MISSING_PARAM', message: 'Query parameter "model" is required.' } });
        const recordId = parseInt(id);
        if (isNaN(recordId) || recordId <= 0) return formatResponse(reply, { statusCode: 400, error: { code: 'INVALID_PARAM', message: `Invalid ID: ${id}.` } });

        // Tentukan fields yang akan diminta
        let fieldsToRequest;
        if (detailMode) {
            fieldsToRequest = explicitlyRequestedFields;
            request.log.info({ reqId, model, recordId }, `Detail mode TRUE. Requesting fields: ${fieldsToRequest ? `[${fieldsToRequest.join(', ')}]` : 'ALL (Default)'}`);
        } else {
            const validFieldNames = await getValidFieldsForModel(con, model, request); // Gunakan helper
             if (validFieldNames.length === 0) {
                 request.log.warn({ reqId, model, recordId }, 'Could not get valid fields, defaulting to id, display_name');
                 fieldsToRequest = ['id', 'display_name'];
             } else {
                const actualMinimalFields = POTENTIAL_MINIMAL_FIELDS.filter(field => validFieldNames.includes(field));
                request.log.info({ reqId, model, recordId, potential: POTENTIAL_MINIMAL_FIELDS.join(','), valid_count: validFieldNames.length, filtered: actualMinimalFields.join(',') }, 'Filtering minimal fields');
                const baseValid = BASE_MINIMAL_FIELDS.filter(f => validFieldNames.includes(f));
                fieldsToRequest = [...new Set([...baseValid, ...actualMinimalFields])];
                if (fieldsToRequest.length === 0) {
                    fieldsToRequest = validFieldNames.includes('id') ? ['id'] : [];
                    request.log.warn({ reqId, model, recordId, final_fallback: fieldsToRequest.join(',') }, 'No minimal fields were valid, falling back');
                }
             }
             request.log.info({ reqId, model, recordId }, `Detail mode FALSE. Final fields to request: [${fieldsToRequest.join(', ')}]`);
        }

        // Panggil con.read
        request.log.info({ reqId, model, recordId, fields: fieldsToRequest || 'DEFAULT' }, 'Reading single record...');
        const result = await con.read(model, [recordId], fieldsToRequest, { context: { lang: "en_US" } });
        request.log.info({ reqId, model, recordId }, `Read successful, found ${result.length} record(s)`);


        if (!result || result.length === 0) return formatResponse(reply, { statusCode: 404, error: { code: 'NOT_FOUND', message: `Record ${recordId} not found in model ${model}.` } });

        const selfLink = `${request.protocol}://${request.headers.host}${request.raw.url}`;
        request.log.info({ reqId }, 'Sending successful response');
        return formatResponse(reply, { statusCode: 200, data: result[0], links: { self: selfLink } });

    } catch (error) {
      request.log.error({ reqId, err: error }, `Error in GET /api/be/:id for model "${request.query.model}", ID "${request.params.id}"`);
      // Penanganan error
      if (error.message?.includes('AccessError')) return formatResponse(reply, { statusCode: 403, error: { code: 'FORBIDDEN' } });
      if (error.message?.includes('Model not found')) return formatResponse(reply, { statusCode: 404, error: { code: 'NOT_FOUND' } });
      if (error.message?.includes('Invalid field')) return formatResponse(reply, { statusCode: 400, error: { code: 'INVALID_FIELD', message: error.message } });
      return formatResponse(reply, { statusCode: 500, error: { message: error.message || 'Failed to retrieve record.' } });
    }
  });

  // --- POST, PUT, DELETE Routes (Tetap Sama) ---
  fastify.post('/api/be', async (request, reply) => {
    // ... (kode POST tidak berubah) ...
    try {
        const { username, password } = request.user;
        const con = await fastify.auth(username, password);
        if (!con) throw new Error('Odoo connection failed.');
        const { model } = request.query;
        const createData = request.body;
        if (!model) return formatResponse(reply, { statusCode: 400, error: { code: 'MISSING_PARAM' } });
        if (!createData || typeof createData !== 'object' || Object.keys(createData).length === 0) return formatResponse(reply, { statusCode: 400, error: { code: 'INVALID_BODY' } });

        const newId = await con.create(model, createData);
        if (!newId || typeof newId !== 'number' || newId <= 0) throw new Error('Create failed.');

        const newRecord = await con.read(model, [newId], undefined, { context: { lang: "en_US" } });
        if (!newRecord || newRecord.length === 0) return formatResponse(reply, { statusCode: 201, meta: { message: `Created (ID ${newId}), retrieve failed.`} });

        const selfLink = `${request.protocol}://${request.headers.host}/api/be/${newId}?model=${model}`;
        return formatResponse(reply, { statusCode: 201, data: newRecord[0], meta: { message: `Created (ID ${newId}).` }, links: { self: selfLink } });
    } catch (error) {
        request.log.error(error, `POST /api/be error: ${model}`);
        if (error.message?.includes('ValidationError')) return formatResponse(reply, { statusCode: 400, error: { code: 'VALIDATION_ERROR', message: error.message } });
        if (error.message?.includes('AccessError')) return formatResponse(reply, { statusCode: 403, error: { code: 'FORBIDDEN' } });
        return formatResponse(reply, { statusCode: 500, error: { code: 'CREATE_FAILED', message: error.message } });
    }
  });
  fastify.put('/api/be/:id', async (request, reply) => {
    // ... (kode PUT tidak berubah) ...
     try {
        const { username, password } = request.user;
        const con = await fastify.auth(username, password);
        if (!con) throw new Error('Odoo connection failed.');
        const { id } = request.params;
        const { model } = request.query;
        const updateData = request.body;
        if (!model) return formatResponse(reply, { statusCode: 400, error: { code: 'MISSING_PARAM' } });
        const recordId = parseInt(id);
        if (isNaN(recordId) || recordId <= 0) return formatResponse(reply, { statusCode: 400, error: { code: 'INVALID_PARAM', message: `Invalid ID: ${id}.` } });
        if (!updateData || typeof updateData !== 'object' || Object.keys(updateData).length === 0) return formatResponse(reply, { statusCode: 400, error: { code: 'INVALID_BODY' } });

        const success = await con.write(model, [recordId], updateData);
        if (!success) {
             const existsResult = await con.search(model, [['id', '=', recordId]], { limit: 1 });
             if (existsResult.length === 0) return formatResponse(reply, { statusCode: 404, error: { code: 'NOT_FOUND', message: `Record ${recordId} not found.` } });
             else return formatResponse(reply, { statusCode: 400, error: { code: 'UPDATE_FAILED', message: `Update failed for ${recordId}.` } });
        }
        const updatedRecord = await con.read(model, [recordId], undefined, { context: { lang: "en_US" } });
        if (!updatedRecord || updatedRecord.length === 0) return formatResponse(reply, { statusCode: 200, meta: { message: `Updated, retrieve failed.`} });

        const selfLink = `${request.protocol}://${request.headers.host}${request.raw.url}`;
        return formatResponse(reply, { statusCode: 200, data: updatedRecord[0], meta: { message: `Updated.` }, links: { self: selfLink } });
    } catch (error) {
        request.log.error(error, `PUT /api/be/:id error: ${model}, ${request.params.id}`);
        if (error.message?.includes('ValidationError')) return formatResponse(reply, { statusCode: 400, error: { code: 'VALIDATION_ERROR', message: error.message } });
        if (error.message?.includes('AccessError')) return formatResponse(reply, { statusCode: 403, error: { code: 'FORBIDDEN' } });
        if (error.message?.includes('Record not found')) return formatResponse(reply, { statusCode: 404, error: { code: 'NOT_FOUND' } });
        return formatResponse(reply, { statusCode: 500, error: { code: 'UPDATE_FAILED', message: error.message } });
    }
  });
  fastify.delete('/api/be/:id', async (request, reply) => {
    // ... (kode DELETE tidak berubah) ...
    try {
        const { username, password } = request.user;
        const con = await fastify.auth(username, password);
        if (!con) throw new Error('Odoo connection failed.');
        const { id } = request.params;
        const { model } = request.query;
        if (!model) return formatResponse(reply, { statusCode: 400, error: { code: 'MISSING_PARAM' } });
        const recordId = parseInt(id);
        if (isNaN(recordId) || recordId <= 0) return formatResponse(reply, { statusCode: 400, error: { code: 'INVALID_PARAM', message: `Invalid ID: ${id}.` } });

        const success = await con.unlink(model, [recordId]);
        if (!success) {
             const existsResult = await con.search(model, [['id', '=', recordId]], { limit: 1 });
             if (existsResult.length === 0) return formatResponse(reply, { statusCode: 404, error: { code: 'NOT_FOUND', message: `Record ${recordId} not found.` } });
             else return formatResponse(reply, { statusCode: 400, error: { code: 'DELETE_RESTRICTED', message: `Deletion failed for ${recordId}.` } });
        }
        return formatResponse(reply, { statusCode: 200, meta: { message: `Record ${recordId} deleted.` } });
    } catch (error) {
        request.log.error(error, `DELETE /api/be/:id error: ${model}, ${request.params.id}`);
        if (error.message?.includes('AccessError')) return formatResponse(reply, { statusCode: 403, error: { code: 'FORBIDDEN' } });
        if (error.message?.includes('Record not found')) return formatResponse(reply, { statusCode: 404, error: { code: 'NOT_FOUND' } });
        if (error.message?.includes('constraint')) return formatResponse(reply, { statusCode: 400, error: { code: 'DELETE_RESTRICTED', message: `Constraint error.` } });
        return formatResponse(reply, { statusCode: 500, error: { code: 'DELETE_FAILED', message: error.message } });
    }
  });

}

// Ekspor plugin
export default fp(beApiRoutes, {
  name: 'be-api',
});