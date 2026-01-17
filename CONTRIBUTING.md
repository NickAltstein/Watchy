# Contributing to Watch Trading Engine

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Commit Messages](#commit-messages)
- [Pull Request Process](#pull-request-process)

## Code of Conduct

This project adheres to a code of conduct that all contributors are expected to follow. Please be respectful and constructive in all interactions.

## Getting Started

### Prerequisites

- Node.js 20+ and npm 9+
- Python 3.10+
- Git
- OpenAI API key with GPT-4o access
- DeepSeek API key (optional, for cost savings)

### Initial Setup

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/Watchy.git
   cd Watchy
   ```

3. Install dependencies:
   ```bash
   # Node.js dependencies
   npm install
   
   # Python dependencies
   pip install -r requirements.txt
   ```

4. Set up environment:
   ```bash
   cp .env.template .env
   # Edit .env with your API keys and configuration
   ```

5. Initialize the database:
   ```bash
   python update_target_prices.py
   ```

## Development Workflow

### Branch Naming

Use descriptive branch names with prefixes:

- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation updates
- `refactor/` - Code refactoring
- `test/` - Test additions or updates
- `chore/` - Maintenance tasks

Examples:
- `feature/add-email-notifications`
- `fix/deduplication-logic`
- `docs/update-api-endpoints`

### Running in Development Mode

#### Terminal 1 - Python API:
```bash
npm run api
# or
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

#### Terminal 2 - WhatsApp Listener:
```bash
npm run dev
# or
nodemon server.js
```

#### Terminal 3 - Full Stack (both services):
```bash
npm run dev:full
```

### Testing Your Changes

Before submitting a pull request:

1. Run linters:
   ```bash
   npm run lint
   ```

2. Run tests:
   ```bash
   npm test
   ```

3. Test the API manually:
   ```bash
   curl http://localhost:8000/health
   ```

## Coding Standards

### JavaScript/Node.js

- Use ES6+ features
- Follow Airbnb JavaScript Style Guide
- Use async/await instead of callbacks
- Add JSDoc comments for functions
- Use meaningful variable names
- Keep functions small and focused

Example:
```javascript
/**
 * Processes a watch listing message
 * @param {Object} msg - The WhatsApp message object
 * @returns {Promise<Object>} Parsed watch data
 */
async function processMessage(msg) {
    // Implementation
}
```

### Python

- Follow PEP 8 style guide
- Use type hints
- Add docstrings for all functions and classes
- Use async/await for I/O operations
- Keep imports organized (stdlib, third-party, local)

Example:
```python
async def calculate_deal_score(
    price: int,
    market_price: int,
    multiplier: int = 1000
) -> int:
    """
    Calculate deal score based on price difference.
    
    Args:
        price: Asking price in USD
        market_price: Market reference price in USD
        multiplier: Score multiplier (default: 1000)
    
    Returns:
        Deal score ranging from -500 to 500
    """
    # Implementation
```

### General Guidelines

- **DRY Principle**: Don't Repeat Yourself
- **SOLID Principles**: Follow SOLID design principles
- **Error Handling**: Always handle errors gracefully
- **Logging**: Use appropriate log levels (debug, info, warn, error)
- **Security**: Never commit secrets, API keys, or sensitive data
- **Performance**: Consider performance implications of changes

## Testing Guidelines

### Unit Tests

Write unit tests for:
- Utility functions
- Data parsing logic
- Score calculation
- Validation functions

### Integration Tests

Write integration tests for:
- API endpoints
- Database operations
- External service integrations

### Test Structure

```javascript
describe('Deal Score Calculation', () => {
    it('should return positive score for below-market price', () => {
        const score = calculateScore(10000, 12000);
        expect(score).toBeGreaterThan(0);
    });
    
    it('should return negative score for above-market price', () => {
        const score = calculateScore(15000, 12000);
        expect(score).toBeLessThan(0);
    });
});
```

## Commit Messages

Follow the Conventional Commits specification:

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, no logic change)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks
- `perf`: Performance improvements
- `ci`: CI/CD changes

### Examples

```
feat(dashboard): add real-time price updates via WebSocket

Implemented WebSocket connection to stream live price updates
to the dashboard. Updates are pushed every 5 seconds.

Closes #123
```

```
fix(deduplication): correct time window calculation

Fixed bug where deduplication window was using wrong timezone,
causing duplicates to not be detected properly.

Fixes #456
```

## Pull Request Process

1. **Update your fork**:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make your changes**:
   - Write clean, documented code
   - Add tests for new functionality
   - Update documentation as needed

4. **Test thoroughly**:
   ```bash
   npm run lint
   npm test
   ```

5. **Commit your changes**:
   ```bash
   git add .
   git commit -m "feat: add your feature"
   ```

6. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

7. **Create Pull Request**:
   - Go to GitHub and create a PR from your branch
   - Fill out the PR template completely
   - Link related issues
   - Request review from maintainers

### PR Title Format

Use the same format as commit messages:
```
feat(scope): brief description of changes
```

### PR Description Template

```markdown
## Description
Brief description of what this PR does

## Type of Change
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update

## Testing
Describe the tests you ran to verify your changes

## Checklist
- [ ] My code follows the style guidelines
- [ ] I have performed a self-review
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have made corresponding changes to the documentation
- [ ] My changes generate no new warnings
- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] New and existing unit tests pass locally with my changes
- [ ] Any dependent changes have been merged and published

## Screenshots (if applicable)
Add screenshots to help explain your changes

## Related Issues
Closes #123
Related to #456
```

## Code Review Process

All submissions require review. Reviewers will check for:

1. **Functionality**: Does it work as intended?
2. **Code Quality**: Is it clean, readable, and maintainable?
3. **Tests**: Are there adequate tests?
4. **Documentation**: Is it properly documented?
5. **Performance**: Are there any performance concerns?
6. **Security**: Are there any security issues?

### Addressing Feedback

- Be responsive to review comments
- Make requested changes in new commits
- Don't force-push after receiving reviews
- Mark conversations as resolved when addressed

## Getting Help

If you need help:

1. Check existing documentation
2. Search existing issues
3. Ask questions in GitHub Discussions
4. Reach out to maintainers

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Recognition

Contributors are recognized in:
- GitHub contributors page
- Release notes for significant contributions
- README.md (for major features)

Thank you for contributing to the Watch Trading Engine! 🚀⌚
