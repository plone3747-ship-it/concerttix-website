-- =====================================================================
--  ConcertTix database schema (MySQL 8.0+ / MariaDB 10.6+)
--  Run automatically by `python seed.py`, or manually:
--     mysql -u concerttix -p concerttix < database/schema.sql
-- =====================================================================

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS contact_messages;
DROP TABLE IF EXISTS guarantee_claims;
DROP TABLE IF EXISTS favorites;
DROP TABLE IF EXISTS reviews;
DROP TABLE IF EXISTS tickets;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS concerts;
DROP TABLE IF EXISTS venues;
DROP TABLE IF EXISTS artists;
DROP TABLE IF EXISTS users;
SET FOREIGN_KEY_CHECKS = 1;

-- ---------------------------------------------------------------------
-- Users: customers and administrators
-- ---------------------------------------------------------------------
CREATE TABLE users (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(120)  NOT NULL,
    email       VARCHAR(190)  NOT NULL UNIQUE,
    phone       VARCHAR(40)   NULL,
    password    VARCHAR(255)  NOT NULL,              -- salted hash, never plain text
    role        ENUM('customer','admin') NOT NULL DEFAULT 'customer',
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- Artists
-- ---------------------------------------------------------------------
CREATE TABLE artists (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(150)  NOT NULL,
    image       VARCHAR(255)  NULL,
    genre       VARCHAR(60)   NOT NULL,
    description TEXT          NULL,
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- Venues
-- ---------------------------------------------------------------------
CREATE TABLE venues (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(150)  NOT NULL,
    address     VARCHAR(255)  NOT NULL,
    city        VARCHAR(80)   NOT NULL,
    capacity    INT           NOT NULL DEFAULT 0,
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- Concerts
--   `venue` and `city` are stored as text (as in the brief) AND linked
--   to the venues table through venue_id so admins can pick a venue.
-- ---------------------------------------------------------------------
CREATE TABLE concerts (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    artist_id    INT           NOT NULL,
    venue_id     INT           NULL,
    title        VARCHAR(200)  NOT NULL,
    image        VARCHAR(255)  NULL,
    date         DATE          NOT NULL,
    time         TIME          NOT NULL,
    venue        VARCHAR(150)  NOT NULL,
    city         VARCHAR(80)   NOT NULL,
    genre        VARCHAR(60)   NOT NULL,
    age_limit    VARCHAR(20)   NOT NULL DEFAULT 'All ages',
    description  TEXT          NULL,
    status       ENUM('on_sale','sold_out','cancelled','completed','draft') NOT NULL DEFAULT 'on_sale',
    featured     TINYINT(1)    NOT NULL DEFAULT 0,
    created_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_concert_artist FOREIGN KEY (artist_id) REFERENCES artists(id) ON DELETE RESTRICT,
    CONSTRAINT fk_concert_venue  FOREIGN KEY (venue_id)  REFERENCES venues(id)  ON DELETE SET NULL,
    INDEX idx_concert_date (date),
    INDEX idx_concert_city (city),
    INDEX idx_concert_genre (genre)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- Orders
--   `tickets` = number of tickets in the order. The individual tickets
--   point back here through tickets.order_id.
-- ---------------------------------------------------------------------
CREATE TABLE orders (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    order_ref          VARCHAR(20)   NOT NULL UNIQUE,
    user_id            INT           NOT NULL,
    concert_id         INT           NOT NULL,
    tickets            INT           NOT NULL,
    subtotal           DECIMAL(10,2) NOT NULL,
    service_fee        DECIMAL(10,2) NOT NULL,
    total              DECIMAL(10,2) NOT NULL,          -- always in SGD
    currency           CHAR(3)       NOT NULL DEFAULT 'SGD',
    total_in_currency  DECIMAL(14,2) NOT NULL,          -- what the buyer saw
    customer_name      VARCHAR(120)  NOT NULL,
    customer_email     VARCHAR(190)  NOT NULL,
    customer_phone     VARCHAR(40)   NOT NULL,
    payment_method     ENUM('card','apple_pay','google_pay','paypal') NOT NULL,
    card_last4         CHAR(4)       NULL,               -- demo only, never the full number
    payment_status     ENUM('paid','pending','failed','refunded','cancelled') NOT NULL DEFAULT 'paid',
    order_date         DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_order_user    FOREIGN KEY (user_id)    REFERENCES users(id)    ON DELETE RESTRICT,
    CONSTRAINT fk_order_concert FOREIGN KEY (concert_id) REFERENCES concerts(id) ON DELETE RESTRICT,
    INDEX idx_order_date (order_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- Tickets = seat inventory. One row per seat / standing spot.
--   status: available -> held (10 min during checkout) -> sold
--           blocked = taken off sale by an admin
-- ---------------------------------------------------------------------
CREATE TABLE tickets (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    concert_id     INT           NOT NULL,
    type           ENUM('VVIP','VIP','CAT 1','General Admission') NOT NULL,
    price          DECIMAL(10,2) NOT NULL,
    seat           VARCHAR(12)   NOT NULL,              -- e.g. A12, GA-045
    seat_row       VARCHAR(4)    NULL,
    seat_number    INT           NULL,
    status         ENUM('available','held','sold','blocked') NOT NULL DEFAULT 'available',
    held_by        INT           NULL,
    held_until     DATETIME      NULL,
    order_id       INT           NULL,
    qr_token       VARCHAR(40)   NULL UNIQUE,           -- printed in the QR e-ticket
    checked_in_at  DATETIME      NULL,
    CONSTRAINT fk_ticket_concert FOREIGN KEY (concert_id) REFERENCES concerts(id) ON DELETE CASCADE,
    CONSTRAINT fk_ticket_order   FOREIGN KEY (order_id)   REFERENCES orders(id)   ON DELETE SET NULL,
    UNIQUE KEY uq_concert_seat (concert_id, seat),
    INDEX idx_ticket_status (concert_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- Reviews and favourites
-- ---------------------------------------------------------------------
CREATE TABLE reviews (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT          NOT NULL,
    concert_id  INT          NOT NULL,
    rating      TINYINT      NOT NULL,
    comment     TEXT         NULL,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_review_user    FOREIGN KEY (user_id)    REFERENCES users(id)    ON DELETE CASCADE,
    CONSTRAINT fk_review_concert FOREIGN KEY (concert_id) REFERENCES concerts(id) ON DELETE CASCADE,
    UNIQUE KEY uq_review (user_id, concert_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE favorites (
    user_id     INT      NOT NULL,
    concert_id  INT      NOT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, concert_id),
    CONSTRAINT fk_fav_user    FOREIGN KEY (user_id)    REFERENCES users(id)    ON DELETE CASCADE,
    CONSTRAINT fk_fav_concert FOREIGN KEY (concert_id) REFERENCES concerts(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- Buyer Guarantee claims (invalid ticket / not delivered / cancelled)
-- ---------------------------------------------------------------------
CREATE TABLE guarantee_claims (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    order_id    INT          NOT NULL,
    user_id     INT          NOT NULL,
    reason      ENUM('invalid_ticket','not_delivered','event_cancelled','other') NOT NULL,
    details     TEXT         NULL,
    status      ENUM('open','approved','rejected') NOT NULL DEFAULT 'open',
    admin_note  VARCHAR(255) NULL,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_claim_order FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    CONSTRAINT fk_claim_user  FOREIGN KEY (user_id)  REFERENCES users(id)  ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------
-- Contact form messages
-- ---------------------------------------------------------------------
CREATE TABLE contact_messages (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(120) NOT NULL,
    email       VARCHAR(190) NOT NULL,
    subject     VARCHAR(200) NOT NULL,
    message     TEXT         NOT NULL,
    is_read     TINYINT(1)   NOT NULL DEFAULT 0,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
