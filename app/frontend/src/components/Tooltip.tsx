import Icon from "./Icon";

type TooltipProps = {
  text: string;
};

export default function Tooltip({ text }: TooltipProps) {
  return (
    <span className="tooltip" data-tip={text}>
      <Icon name="info" className="icon icon-inline" />
      <span className="sr-only">{text}</span>
    </span>
  );
}
