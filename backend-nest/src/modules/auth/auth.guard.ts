import {
  CanActivate,
  ExecutionContext,
  Injectable,
  UnauthorizedException,
} from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import { ConfigService } from '@nestjs/config';
import { Request } from 'express';

@Injectable()
export class AuthGuard implements CanActivate {
  constructor(
    private readonly jwtService: JwtService,
    private readonly config: ConfigService,
  ) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const request = context.switchToHttp().getRequest<Request>();
    const token = this.extractToken(request);
    if (!token) throw new UnauthorizedException('Missing token');

    try {
      const secret = this.config.get<string>('jwt.secret', 'changeme');
      request['user'] = await this.jwtService.verifyAsync(token, { secret });
    } catch {
      throw new UnauthorizedException('Invalid token');
    }
    return true;
  }

  private extractToken(request: Request): string | null {
    const auth = request.headers.authorization ?? '';
    const [type, token] = auth.split(' ');
    return type === 'Bearer' ? token : null;
  }
}
