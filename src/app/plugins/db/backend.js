import Odoo from 'odoo-await';
import dotenv from 'dotenv';
import jwt from 'jsonwebtoken';

dotenv.config();

async function fp(fastify, opts) {
    const backendUrl = `${process.env.BASE_URL}:${process.env.BACKEND_ODOO_PORT}`;

    const backend = new Odoo({
        baseUrl: backendUrl,
        port: process.env.BACKEND_ODOO_PORT,
        db: process.env.BACKEND_DB,
        username: "bjo163@gmail.com",  // username from user input
        password: "Youknowm@2025",     // password from user input
    });

    try {
        await backend.connect();
        console.log('Successfully connected to Odoo backend:', backend);

        // Prepare user data (Do not include password)
        const userPayload = {
            user: "bjo163@gmail.com",  // You can also include a user ID or email
            db: process.env.BACKEND_DB,
        };

        // Generate JWT token (Do not include the password in the payload)
        const token = jwt.sign(userPayload, process.env.JWT_SECRET, { expiresIn: '1h' });

        // Send the token as response
        fastify.send({ message: 'Login successful', token });

    } catch (error) {
        console.error('Error connecting to Odoo:', error);
        fastify.send({ error: 'Failed to connect to Odoo' });
    }
}

export default fp;
