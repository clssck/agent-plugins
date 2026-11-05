module "orders_bucket" {
  source  = "git::https://github.com/acme/terraform-aws-library.git//modules/s3?ref=v3.2.0"
  name    = "acme-orders-exports"
  tags    = local.tags
}

resource "aws_security_group" "api" {
  name = "orders-api"
  ingress {
    from_port   = 0
    to_port     = 65535
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_iam_policy" "worker" {
  name   = "orders-worker"
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "*", Resource = "*" }] })
}
