var Chart = function(parent, colour) {
  var margin = {top: 10, right: 10, bottom: 0, left: 40}
    , n = 200
    , random = d3.random.normal(0, .2)
    , width = 900 - margin.left - margin.right
    , height = 350 - margin.top - margin.bottom
    , duration = 1000
    , now = new Date(Date.now() - duration);

  this.data = d3.range(n).map(function() { return 0; });

  var x = d3.time.scale()
    .domain([now - (n - 2) * duration, now - duration])
    .range([0, width]);

  x.axis = d3.svg.axis().scale(x).orient("bottom").ticks(6);

  var create_y_axis = function() {
    return d3.svg.axis().scale(y).orient("left");
  };

  var y = d3.scale.linear()
      .domain([0, 50])
      .range([height, 0]);
  y.axis = create_y_axis();

  var line = d3.svg.line()
    .x(function(d, i) { return x(now - (n - 1 - i) * duration); })
    .y(function(d, i) { return y(d); });

  var area = d3.svg.area()
    .x(function(d, i) { return x(now - (n - 1 -i) * duration); })
    .y0(function(d, i) { return height; })
    .y1(function(d, i) { return y(d); });

  var svg = d3.select(parent)
    .append("svg")
      .attr("width", width + margin.left + margin.right)
      .attr("height", height + margin.top + margin.bottom + 40)
      .append("g")
        .attr("transform", "translate("+margin.left+", "+margin.top+")");

  svg.append("defs").append("clipPath")
      .attr("id", "clip")
    .append("rect")
      .attr("width", width)
      .attr("height", height);

  svg.append("g").classed("grid y_grid", true)
      .call(create_y_axis().tickSize(-width, 0, 0).tickFormat(""));

  var pathFill = svg.append("g")
      .attr("clip-path", "url(#clip)")
    .append("path")
      .data([this.data])
      .attr("class", "area " + colour + "-area")
      .attr("d", area)
      .attr("opacity", "0.4");

  var axis = svg.append("g")
      .attr("class", "x axis")
      .attr("transform", "translate(0, "+height+")")
      .call(x.axis);

  var path = svg.append("g")
      .attr("clip-path", "url(#clip)")
    .append("path")
      .data([this.data])
      .attr("class", "line " + colour + "-line")
      .attr("d", line);

  svg.append("g")
      .attr("class", "y axis")
      .call(y.axis);

  this.tick = function() {
    now = new Date();
    x.domain([now - (n - 10) * duration, now - duration]);

    axis
      .call(x.axis);

    path
      .attr("d", line)
      .attr("transform", null)
      .transition()
        .duration(duration)
        .ease("linear")
        .attr("transform", "translate("+x(now - (n-10) * duration)+")");

    pathFill
      .attr("d", area)
      .attr("transform", null)
      .transition()
        .duration(duration)
        .ease("linear")
        .attr("transform", "translate("+x(now - (n-10) * duration)+")");

    this.data.shift();
  }
}
