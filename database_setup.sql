-- Création de la table images
CREATE TABLE IF NOT EXISTS images (
    id SERIAL PRIMARY KEY,
    category VARCHAR(50) NOT NULL,
    image_url TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP NULL
);

-- Index pour optimiser les recherches
CREATE INDEX idx_category_status ON images(category, status);
CREATE INDEX idx_status ON images(status);

-- Vérifier la structure
SELECT 
    column_name, 
    data_type, 
    character_maximum_length,
    is_nullable,
    column_default
FROM 
    information_schema.columns
WHERE 
    table_name = 'images'
ORDER BY 
    ordinal_position;
