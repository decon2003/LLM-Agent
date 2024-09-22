const express = require('express');
const app = express();

// Vulnerable XSS page
app.get('/', (req, res) => {
    const userInput = req.query.input || '';
    
    // This code is intentionally vulnerable to XSS
    res.send(`
        <html>
        <head>
            <title>Vulnerable XSS Test Page</title>
        </head>
        <body>
            <h1>Vulnerable XSS Test Page</h1>
            <form method="GET">
                <label for="input">Enter something (XSS test):</label>
                <input type="text" id="input" name="input">
                <button type="submit">Submit</button>
            </form>
            <p>You entered: ${userInput}</p> <!-- Vulnerable to XSS -->
        </body>
        </html>
    `);
});

app.listen(3000, () => {
    console.log('Server running at http://localhost:3000');
});
