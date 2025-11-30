CREATE TABLE IF NOT EXISTS images (
  id SERIAL PRIMARY KEY,
  image_url TEXT NOT NULL,
  category TEXT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  inserted_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  sent_at TIMESTAMP WITH TIME ZONE NULL
);

CREATE INDEX IF NOT EXISTS idx_images_category_status ON images (category, status);
