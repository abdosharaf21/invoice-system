-- Phase 6.5: Application & Organization Settings
-- Adds application_settings (key/value), extends companies and users with preference columns.

CREATE TABLE IF NOT EXISTS `application_settings` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `setting_key` VARCHAR(100) NOT NULL,
    `setting_value` TEXT DEFAULT NULL,
    `value_type` VARCHAR(20) NOT NULL DEFAULT 'string',
    `description` VARCHAR(255) DEFAULT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_application_settings_key` (`setting_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Default application settings
INSERT IGNORE INTO `application_settings` (`setting_key`, `setting_value`, `value_type`, `description`) VALUES
    ('application_name', 'E-Invoice & Reconciliation', 'string', 'Display name of the application'),
    ('application_subtitle', 'Tax authority compliance', 'string', 'Subtitle shown in the sidebar'),
    ('default_language', 'en', 'string', 'Default UI language code'),
    ('default_theme', 'light', 'string', 'Default theme (light or dark)'),
    ('date_format', 'YYYY-MM-DD', 'string', 'Default date display format'),
    ('number_format', '#,##0.00', 'string', 'Default number display format'),
    ('timezone', 'UTC', 'string', 'Default timezone'),
    ('pagination_size', '25', 'integer', 'Default page size for tables');

-- Extend companies table with settings columns (appended after updated_at so
-- existing positional row mapping in CompanyRepository stays valid)
ALTER TABLE `companies`
    ADD COLUMN `logo_path` VARCHAR(500) DEFAULT NULL AFTER `updated_at`,
    ADD COLUMN `website` VARCHAR(255) DEFAULT NULL AFTER `logo_path`,
    ADD COLUMN `default_currency` VARCHAR(3) DEFAULT 'EGP' AFTER `website`,
    ADD COLUMN `default_tax_rate` DECIMAL(5,2) DEFAULT 0.00 AFTER `default_currency`,
    ADD COLUMN `fiscal_year_start` VARCHAR(10) DEFAULT '01-01' AFTER `default_tax_rate`;

-- Extend users table with preference columns (appended after updated_at so
-- existing positional row mapping in UserRepository stays valid)
ALTER TABLE `users`
    ADD COLUMN `language` VARCHAR(10) DEFAULT 'en' AFTER `updated_at`,
    ADD COLUMN `theme` VARCHAR(20) DEFAULT 'light' AFTER `language`,
    ADD COLUMN `date_format` VARCHAR(20) DEFAULT 'YYYY-MM-DD' AFTER `theme`,
    ADD COLUMN `number_format` VARCHAR(20) DEFAULT '#,##0.00' AFTER `date_format`,
    ADD COLUMN `timezone` VARCHAR(50) DEFAULT 'UTC' AFTER `number_format`,
    ADD COLUMN `avatar_path` VARCHAR(500) DEFAULT NULL AFTER `timezone`,
    ADD COLUMN `pagination_size` INT UNSIGNED DEFAULT 25 AFTER `avatar_path`;
