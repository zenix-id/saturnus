import fp from 'fastify-plugin';
import { ZENIX_API_AUTH_USER,ZENIX_API_AUTH_PASS } from '../../config/server.js';
import crypto from 'crypto';
import axios from 'axios';
async function beApiOauthRoutes(fastify, opts) {



  // --- GET /api/be (List resources or models) ---

  fastify.post('/api/oauth', async (request, reply) => {
    const { login, name, image } = request.body || {};
  
    if (!login) {
      return reply.status(400).send({
        statusCode: 400,
        message: 'Field "login" diperlukan.'
      });
    }
  
    try {
      const con = await fastify.auth(ZENIX_API_AUTH_USER, ZENIX_API_AUTH_PASS);
      let user, password;
  
      // Cek user
      const res = await con.searchRead('res.users', { login });
  
      if (res?.length > 0) {
        user = res[0];
        const secrets = await con.searchRead('zms.secret.vault', { user_id: user.id });
        password = secrets?.[0]?.password;
  
        if (!password) {
          console.warn('Password tidak ditemukan di vault untuk user:', login);
        }
  
      } else {
        // Buat password acak
        password = crypto.randomBytes(4).toString('hex');
        console.log(`Membuat user baru ${login} dengan password: ${password}`);
  
        // Konversi gambar
        let imageBase64 = null;
        if (image) {
          try {
            const response = await axios.get(image, { responseType: 'arraybuffer' });
            imageBase64 = Buffer.from(response.data, 'binary').toString('base64');
          } catch (imgErr) {
            console.warn("Gagal mengunduh gambar:", imgErr.message);
          }
        }
  
        // Buat user baru
        const newUser = {
          login,
          name: name || login,
          password,
          ...(imageBase64 ? { image_1920: imageBase64 } : {})
        };
        const createdId = await con.create('res.users', newUser);
        await con.create('zms.secret.vault', {
          user_id: createdId,
          name: name || login,
          password
        });
  
        // Ambil data user hasil create
        user = { id: createdId, login, name: name || login };
      }
  
      // 🔐 Login ke API eksternal
      try {
        const extRes = await axios.post('http://127.0.0.1:4000/api/auth', {
          username: login,
          password: password
        }, {
          headers: { 'Content-Type': 'application/json' }
        });
  
        const tokenData = extRes.data;
  
        return reply.send({
          statusCode: 200,
          message: 'Login berhasil.',
          user,
          password,
          tokenData
        });
  
      } catch (authErr) {
        console.error('Login ke API eksternal gagal:', authErr.message);
        return reply.status(500).send({
          statusCode: 500,
          message: 'User berhasil diproses, tetapi login ke API eksternal gagal.',
          error: authErr.message,
          user,
          password
        });
      }
  
    } catch (error) {
      console.error('Terjadi kesalahan utama:', error);
      return reply.status(500).send({
        statusCode: 500,
        message: 'Terjadi kesalahan saat memproses permintaan.',
        error: error.message
      });
    }
  });
  

  



}

// Ekspor plugin
export default fp(beApiOauthRoutes, {
  name: 'be-api-oauth',
});