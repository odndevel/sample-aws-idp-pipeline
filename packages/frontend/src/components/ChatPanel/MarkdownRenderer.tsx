import { Children, isValidElement } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeRaw from 'rehype-raw';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';
import MermaidBlock from './MermaidBlock';

const components: Components = {
  // Override <pre> instead of <code> to avoid invalid <div> inside <pre> nesting.
  // Fenced code blocks render as <pre><code class="language-xxx">...</code></pre>.
  pre({ children, ...props }) {
    const child = Children.toArray(children)[0];
    if (isValidElement(child)) {
      const childProps = child.props as {
        className?: string;
        children?: React.ReactNode;
      };
      if (/language-mermaid/.test(childProps.className || '')) {
        const code = String(childProps.children).replace(/\n$/, '');
        return <MermaidBlock code={code} />;
      }
    }
    return <pre {...props}>{children}</pre>;
  },
};

interface MarkdownRendererProps {
  children: string;
}

export default function MarkdownRenderer({ children }: MarkdownRendererProps) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeRaw]}
      components={components}
    >
      {children}
    </ReactMarkdown>
  );
}
