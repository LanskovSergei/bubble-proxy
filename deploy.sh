#!/bin/bash

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROJECT_NAME="bubble-proxy"
ENV_FILE=".env"

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

info() {
    echo "[INFO] $1"
}

check_env() {
    [ ! -f "$ENV_FILE" ] && error ".env file not found! Copy .env.example to .env and configure it."
    
    source "$ENV_FILE"
    
    [ -z "$DOMAIN" ] && error "DOMAIN is not set in .env"
    [ -z "$BUBBLE_DOMAIN" ] && error "BUBBLE_DOMAIN is not set in .env"
    [ -z "$SSL_EMAIL" ] && error "SSL_EMAIL is not set in .env"
    
    success ".env file validated"
}

create_dirs() {
    info "Creating necessary directories..."
    mkdir -p certbot/www certbot/conf logs/nginx logs/certbot logs/monitor
    success "Directories created"
}

prepare_nginx_config() {
    info "Preparing nginx configuration..."
    
    source "$ENV_FILE"
    
    sed -e "s/\${DOMAIN}/$DOMAIN/g" \
        -e "s/\${BUBBLE_DOMAIN}/$BUBBLE_DOMAIN/g" \
        nginx/conf.d/default.conf.template > nginx/conf.d/default.conf
    
    success "Nginx configuration prepared"
}

init_ssl() {
    info "Initializing SSL certificate..."
    
    source "$ENV_FILE"
    
    cat > nginx/conf.d/default.conf <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 200 "Certbot initialization in progress...";
        add_header Content-Type text/plain;
    }
}
EOF

    info "Starting nginx for certificate validation..."
    docker-compose up -d nginx
    
    sleep 5
    
    info "Requesting SSL certificate from Let's Encrypt..."
    docker-compose run --rm certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        --email "$SSL_EMAIL" \
        --agree-tos \
        --no-eff-email \
        -d "$DOMAIN"
    
    if [ $? -eq 0 ]; then
        success "SSL certificate obtained successfully"
        
        prepare_nginx_config
        
        docker-compose restart nginx
        
        success "Nginx restarted with SSL configuration"
    else
        error "Failed to obtain SSL certificate"
    fi
}

start() {
    info "Starting $PROJECT_NAME..."
    check_env
    create_dirs
    prepare_nginx_config
    
    docker-compose up -d
    
    success "$PROJECT_NAME started successfully"
    info "Check status: ./deploy.sh status"
    info "View logs: ./deploy.sh logs"
}

stop() {
    info "Stopping $PROJECT_NAME..."
    docker-compose down
    success "$PROJECT_NAME stopped"
}

restart() {
    info "Restarting $PROJECT_NAME..."
    stop
    sleep 2
    start
}

logs() {
    if [ -n "$2" ]; then
        docker-compose logs -f "$2"
    else
        docker-compose logs -f
    fi
}

status() {
    docker-compose ps
    
    echo ""
    info "Nginx status:"
    docker-compose exec nginx nginx -t 2>&1 || true
    
    echo ""
    info "SSL certificates:"
    docker-compose run --rm certbot certificates || true
}

update_config() {
    info "Updating configuration..."
    check_env
    prepare_nginx_config
    
    info "Reloading nginx..."
    docker-compose exec nginx nginx -s reload
    
    success "Configuration updated"
}

check_ssl() {
    source "$ENV_FILE"
    
    info "Checking SSL certificate for $DOMAIN..."
    
    echo | openssl s_client -servername "$DOMAIN" -connect "$DOMAIN:443" 2>/dev/null | \
        openssl x509 -noout -dates
}

backup() {
    BACKUP_NAME="backup_$(date +%Y%m%d_%H%M%S).tar.gz"
    
    info "Creating backup: $BACKUP_NAME..."
    
    tar -czf "$BACKUP_NAME" \
        --exclude='logs' \
        --exclude='*.log' \
        .env \
        certbot/conf \
        nginx/conf.d/default.conf
    
    success "Backup created: $BACKUP_NAME"
}

restore() {
    if [ -z "$2" ]; then
        error "Usage: $0 restore <backup_file.tar.gz>"
    fi
    
    BACKUP_FILE="$2"
    
    if [ ! -f "$BACKUP_FILE" ]; then
        error "Backup file not found: $BACKUP_FILE"
    fi
    
    info "Restoring from backup: $BACKUP_FILE..."
    
    warning "This will overwrite current configuration!"
    read -p "Continue? (y/N): " -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        info "Restore cancelled"
        exit 0
    fi
    
    tar -xzf "$BACKUP_FILE"
    
    success "Backup restored"
    info "Run './deploy.sh restart' to apply changes"
}

test_monitor() {
    info "Running manual health check..."
    docker-compose run --rm monitor python /app/check.py
}

show_help() {
    cat <<EOF
Usage: $0 <command> [options]

Commands:
    init            First time setup (get SSL certificate)
    start           Start all services
    stop            Stop all services
    restart         Restart all services
    logs [service]  Show logs (optionally for specific service)
    status          Show services status
    update-config   Update nginx configuration from .env
    check-ssl       Check SSL certificate expiration
    backup          Create backup of configuration and certificates
    restore <file>  Restore from backup
    test-monitor    Run manual health check
    help            Show this help message

Examples:
    $0 init                    # First time setup
    $0 start                   # Start proxy
    $0 logs nginx              # Show nginx logs
    $0 restart                 # Restart all services
    $0 backup                  # Create backup
    $0 restore backup.tar.gz   # Restore from backup

EOF
}

case "$1" in
    init)
        check_env
        create_dirs
        init_ssl
        info "Initialization complete!"
        info "Now run: ./deploy.sh start"
        ;;
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    logs)
        logs "$@"
        ;;
    status)
        status
        ;;
    update-config)
        update_config
        ;;
    check-ssl)
        check_ssl
        ;;
    backup)
        backup
        ;;
    restore)
        restore "$@"
        ;;
    test-monitor)
        test_monitor
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        error "Unknown command: $1"
        echo ""
        show_help
        exit 1
        ;;
esac
