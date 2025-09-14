provider "aws" {
  region = "us-east-2"
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}
resource "aws_instance" "web1" {
  ami = "ami-0634f3c109dcdc659"
  instance_type = "t3.micro"
  subnet_id = data.aws_subnets.default.ids[0]
  user_data = <<-EOF
              #!/bin/bash
              yum install -y nginx
              systemctl enable nginx
              systemctl start nginx
              echo "Hello from WS-1" > /usr/share/nginx/html/index.html
              EOF
  tags = {
    Name = "WS-1"
  }
}
resource "aws_instance" "web2" {
  ami = "ami-0634f3c109dcdc659"
  instance_type = "t3.micro"
  subnet_id = data.aws_subnets.default.ids[1]
  user_data = <<-EOF
              #!/bin/bash
              yum install -y nginx
              systemctl enable nginx
              systemctl start nginx
              echo "Hello from WS-2" > /usr/share/nginx/html/index.html
              EOF
  tags = {
    Name = "WS-2"
  }
}

resource "aws_lb" "app_lb" {
  name               = "web-alb"
  internal           = false
  load_balancer_type = "application"
  subnets = [
    data.aws_subnets.default.ids[0],
    data.aws_subnets.default.ids[1]
  ]
}
resource "aws_lb_target_group" "tg" {
  name     = "web-tg"
  port     = 80
  protocol = "HTTP"
  vpc_id   = data.aws_vpc.default.id

  health_check {
    path                = "/."
    interval            = 5
    timeout             = 4
    healthy_threshold   = 2
    unhealthy_threshold = 2
    matcher             = "200"
  }
}


resource "aws_lb_target_group_attachment" "web1" {
  target_group_arn = aws_lb_target_group.tg.arn
  target_id        = aws_instance.web1.id
  port             = 80
}
resource "aws_lb_target_group_attachment" "web2" {
  target_group_arn = aws_lb_target_group.tg.arn
  target_id        = aws_instance.web2.id
  port             = 80
}


resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.app_lb.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.tg.arn
  }
}

output "alb_dns_name" {
  value = aws_lb.app_lb.dns_name
}
