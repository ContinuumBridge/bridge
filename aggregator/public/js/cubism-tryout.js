var context = cubism.context()
  .serverDelay(0)
  .clientDelay(1000)
  .step(100)
  .size(400);

function data() {
  var value = 0
    , values = []
    , i = 0
    , last;

  return context.metric(function(start, stop, step, callback) {
    start = +start, stop = +stop;
    if (isNaN(last)) {
      last = start;
      timeSlice = (start - stop) / step;
    }

    while (last < stop) {
      last += step;
      value = timeSeries[last] ? timeSeries[last] : 0;
      values.push(value);
    }
    callback(null, values = values.slice((start - stop) / step));
  }, "timeData");
}

var voltageData = data();

d3.select('#voltage-time2').call(function(div) {
  div.append("div")
  .attr("class", "axis")
  .call(context.axis().orient("top"));

  div.selectAll(".horizon")
      .data([voltageData])
    .enter().append("div")
      .attr("class", "horizon")
      .call(context.horizon()
        .height(120)
        .extent([0, 5]));

  div.append("div")
    .attr("class", "rule")
    .call(context.rule());
});

