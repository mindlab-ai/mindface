"""
iresnet.
"""
from mindspore import nn, ops
from mindspore.common.initializer import initializer, HeNormal

__all__ = ['iresnet18', 'iresnet34', 'iresnet50', 'iresnet100']


def conv3x3(in_planes, out_planes, stride=1, groups=1, dilation=1):
    """
    3x3 convolution with padding.
    """
    return nn.Conv2d(in_planes,
                     out_planes,
                     kernel_size=3,
                     stride=stride,
                     padding=dilation,
                     pad_mode='pad',
                     group=groups,
                     has_bias=False,
                     dilation=dilation)


def conv1x1(in_planes, out_planes, stride=1):
    """
    1x1 convolution.
    """
    return nn.Conv2d(in_planes,
                     out_planes,
                     kernel_size=1,
                     stride=stride,
                     has_bias=False)


class IBasicBlock(nn.Cell):
    '''
    IBasicBlock.
    '''
    expansion = 1

    def __init__(self, inplanes, planes, stride=1, downsample=None,
                 groups=1, base_width=64, dilation=1):
        super().__init__()
        if groups != 1 or base_width != 64:
            raise ValueError(
                'BasicBlock only supports groups=1 and base_width=64')
        if dilation > 1:
            raise NotImplementedError(
                "Dilation > 1 not supported in BasicBlock")

        self.bn1 = nn.BatchNorm2d(
            inplanes,
            eps=1e-05,
        )
        self.conv1 = conv3x3(inplanes, planes)
        self.bn2 = nn.BatchNorm2d(
            planes,
            eps=1e-05,
        )
        self.prelu = nn.PReLU(planes)
        self.conv2 = conv3x3(planes, planes, stride)
        self.bn3 = nn.BatchNorm2d(
            planes,
            eps=1e-05,
        )
        self.downsample = downsample
        self.stride = stride

    def construct(self, x):
        """
        construct.
        """
        identity = x

        out = self.bn1(x)
        out = self.conv1(out)
        out = self.bn2(out)
        out = self.prelu(out)
        out = self.conv2(out)
        out = self.bn3(out)

        if self.downsample is not None:
            identity = self.downsample(x)

        out += identity

        return out


class IResNet(nn.Cell):
    """
    Build the iresnet model.

    Args:
        block (Object): The basic block of backbone.
        layers (List): The layer list of resnet.
        dropout (Float): Dropout setting. Default: 0.
        num_features (Int): The num of features. Default: 512.
        groups (Int): The num of groups. Default: 1.
        width_per_group (Int): The width of per group. Default: 64.
        replace_stride_with_dilation (Bool): Replacing stride with dilation. Default: None.

    Examples:
        >>> model = IResNet(block, layers, **kwargs)
    """
    fc_scale = 7 * 7

    def __init__(self,
                 block, layers, dropout=0, num_features=512,
                 groups=1, width_per_group=64, replace_stride_with_dilation=None):
        super().__init__()
        self.inplanes = 64
        self.dilation = 1
        if replace_stride_with_dilation is None:
            replace_stride_with_dilation = [False, False, False]
        if len(replace_stride_with_dilation) != 3:
            raise ValueError(f"replace_stride_with_dilation should be None\
                             or a 3-element tuple, got {replace_stride_with_dilation}")
        self.groups = groups
        self.base_width = width_per_group
        self.conv1 = nn.Conv2d(3, self.inplanes, kernel_size=3,
                               stride=1, padding=1, pad_mode='pad', has_bias=False)
        self.bn1 = nn.BatchNorm2d(self.inplanes, eps=1e-05)
        self.prelu = nn.PReLU(self.inplanes)
        self.layer1 = self._make_layer(block, 64, layers[0], stride=2)
        self.layer2 = self._make_layer(block,
                                       128,
                                       layers[1],
                                       stride=2,
                                       dilate=replace_stride_with_dilation[0])
        self.layer3 = self._make_layer(block,
                                       256,
                                       layers[2],
                                       stride=2,
                                       dilate=replace_stride_with_dilation[1])
        self.layer4 = self._make_layer(block,
                                       512,
                                       layers[3],
                                       stride=2,
                                       dilate=replace_stride_with_dilation[2])
        self.bn2 = nn.BatchNorm2d(512 * block.expansion, eps=1e-05,)
        self.dropout = nn.Dropout(keep_prob=1.0-dropout)
        self.fc = nn.Dense(512 * block.expansion * self.fc_scale,
                           num_features)
        self.features = nn.BatchNorm1d(num_features, eps=1e-05)
        self.features.gamma.requires_grad = False
        self.reshape = ops.Reshape()
        self.flatten = ops.Flatten()
        self._initialize_weights()


    def _make_layer(self, block, planes, blocks, stride=1, dilate=False):
        """
        make_layer.
        """
        downsample = None
        previous_dilation = self.dilation
        if dilate:
            self.dilation *= stride
            stride = 1
        if stride != 1 or self.inplanes != planes * block.expansion:
            downsample = nn.SequentialCell([
                conv1x1(self.inplanes, planes * block.expansion, stride),
                nn.BatchNorm2d(planes * block.expansion, eps=1e-05)
            ])
        layers = []
        layers.append(
            block(self.inplanes, planes, stride, downsample, self.groups,
                  self.base_width, previous_dilation))
        self.inplanes = planes * block.expansion
        for _ in range(1, blocks):
            layers.append(
                block(self.inplanes,
                      planes,
                      groups=self.groups,
                      base_width=self.base_width,
                      dilation=self.dilation))

        return nn.SequentialCell(layers)


    def _initialize_weights(self):
        """
        initialize_weights.
        """
        for _, cell in self.cells_and_names():
            if isinstance(cell, nn.Conv2d):
                cell.weight.set_data(initializer(HeNormal(mode='fan_out', nonlinearity='relu'),
                                                cell.weight.data.shape, cell.weight.data.dtype))
                if cell.bias is not None:
                    cell.bias.set_data(initializer('zeros', cell.bias.data.shape,
                                                cell.bias.data.dtype))
            elif isinstance(cell, nn.BatchNorm2d):
                cell.gamma.set_data(initializer('ones', cell.gamma.data.shape))
                cell.beta.set_data(initializer('zeros', cell.beta.data.shape))
            elif isinstance(cell, nn.Dense):
                cell.weight.set_data(initializer(HeNormal(mode='fan_out', nonlinearity='relu'),
                                                cell.weight.data.shape, cell.weight.data.dtype))
                if cell.bias is not None:
                    cell.bias.set_data(initializer('zeros', cell.bias.data.shape,
                                                cell.bias.data.dtype))


    def construct(self, x):
        """
        construct.
        """
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.prelu(x)

        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)

        x = self.bn2(x)
        x = self.flatten(x)
        x = self.dropout(x)
        x = self.fc(x)
        x = self.features(x)

        return x


def _iresnet(_, block, layers, pretrained, *_progress, **kwargs):
    model = IResNet(block, layers, **kwargs)
    if pretrained:
        raise ValueError()
    return model


def iresnet18(pretrained=False, progress=True, **kwargs):
    """
    Iresnet18.

    Examples:
        >>> net = iresnet18()
    """
    return _iresnet('iresnet18', IBasicBlock, [2, 2, 2, 2], pretrained,
                    progress, **kwargs)


def iresnet34(pretrained=False, progress=True, **kwargs):
    """
    Iresnet34.

    Examples:
        >>> net = iresnet34()
    """
    return _iresnet('iresnet34', IBasicBlock, [3, 4, 6, 3], pretrained,
                    progress, **kwargs)


def iresnet50(pretrained=False, progress=True, **kwargs):
    """
    Iresnet50.

    Examples:
        >>> net = iresnet50()
    """
    return _iresnet('iresnet50', IBasicBlock, [3, 4, 14, 3], pretrained,
                    progress, **kwargs)


def iresnet100(pretrained=False, progress=True, **kwargs):
    """
    Iresnet100.

    Examples:
        >>> net = iresnet100()
    """
    return _iresnet('iresnet100', IBasicBlock, [3, 13, 30, 3], pretrained,
                    progress, **kwargs)
